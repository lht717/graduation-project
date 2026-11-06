const demoUser = {
  username: "demo",
  account_id: "20240001",
  display_name: "演示用户",
  role: "user",
  role_name: "普通用户",
  registered_at: "2025-01-15T08:30:00+08:00"
};

const adminUser = {
  username: "admin",
  account_id: "20240000",
  display_name: "系统管理员",
  role: "admin",
  role_name: "管理员",
  registered_at: "2024-06-01T10:00:00+08:00"
};

let activeUser = null;
const ordinaryUsers = [{ ...demoUser }];
const managedPasswords = new Map();
const privateMessages = [];
let nextMessageId = 1;

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" }
  });
}

async function readJson(request) {
  const text = await request.text();
  return text ? JSON.parse(text) : {};
}

async function handleMockRequest(request, url) {
  const method = request.method.toUpperCase();

  if (url.pathname === "/api/auth/me" && method === "GET") {
    return jsonResponse({
      authenticated: Boolean(activeUser),
      user: activeUser || demoUser
    });
  }

  if (url.pathname === "/api/auth/login" && method === "POST") {
    const body = await readJson(request);
    const username = String(body.username || "").trim();
    const password = String(body.password || "");
    if (!username || !password) {
      return jsonResponse({ detail: "请输入账号和密码" }, 400);
    }
    if (username.toLowerCase() === "admin") {
      activeUser = { ...adminUser };
    } else {
      const managedUser = ordinaryUsers.find((item) => item.username === username);
      if (managedUser && managedPasswords.has(username) && managedPasswords.get(username) !== password) {
        return jsonResponse({ detail: "账号或密码错误" }, 401);
      }
      activeUser = managedUser
        ? { ...managedUser }
        : {
            ...demoUser,
            username,
            account_id: /^\d+$/.test(username) ? username : demoUser.account_id,
            display_name: username.toLowerCase() === "demo" ? demoUser.display_name : username
          };
    }
    return jsonResponse({ authenticated: true, user: activeUser });
  }

  if (url.pathname === "/api/auth/logout" && method === "POST") {
    activeUser = null;
    return jsonResponse({ success: true });
  }

  if (url.pathname === "/api/users/me/password" && method === "POST") {
    const body = await readJson(request);
    if (!body.current_password || !body.new_password) {
      return jsonResponse({ detail: "请填写当前密码和新密码" }, 400);
    }
    return jsonResponse({ message: "密码修改成功" });
  }

  if (url.pathname === "/api/users/me/display-name" && method === "POST") {
    const body = await readJson(request);
    const displayName = String(body.display_name || "").trim();
    if (!displayName) {
      return jsonResponse({ detail: "自定义名称不能为空" }, 400);
    }
    activeUser = { ...(activeUser || demoUser), display_name: displayName };
    const managedUser = ordinaryUsers.find((item) => item.username === activeUser.username);
    if (managedUser) managedUser.display_name = displayName;
    return jsonResponse({ user: activeUser, message: "自定义名称修改成功" });
  }

  if (url.pathname === "/api/admin/users") {
    if (!activeUser || activeUser.role !== "admin") {
      return jsonResponse({ detail: "需要管理员权限" }, 403);
    }
    if (method === "GET") {
      return jsonResponse({ users: ordinaryUsers.map((item) => ({ ...item })) });
    }
    if (method === "POST") {
      const body = await readJson(request);
      const username = String(body.username || "").trim();
      const displayName = String(body.display_name || "").trim();
      const password = String(body.password || "");
      if (!/^\d+$/.test(username)) return jsonResponse({ detail: "账号（学号）必须为数字" }, 400);
      if (!displayName) return jsonResponse({ detail: "请输入自定义名称" }, 400);
      if (password.length < 8) return jsonResponse({ detail: "初始密码至少需要 8 位" }, 400);
      if (ordinaryUsers.some((item) => item.username === username)) {
        return jsonResponse({ detail: "该账号已存在" }, 409);
      }
      const newUser = {
        username,
        account_id: username,
        display_name: displayName,
        role: "user",
        role_name: "普通用户",
        registered_at: new Date().toISOString()
      };
      ordinaryUsers.push(newUser);
      managedPasswords.set(username, password);
      return jsonResponse({ user: { ...newUser }, message: "用户创建成功" }, 201);
    }
  }

  const userRoute = url.pathname.match(/^\/api\/admin\/users\/([^/]+)(?:\/password)?$/);
  if (userRoute) {
    if (!activeUser || activeUser.role !== "admin") {
      return jsonResponse({ detail: "需要管理员权限" }, 403);
    }
    const username = decodeURIComponent(userRoute[1]);
    const user = ordinaryUsers.find((item) => item.username === username);
    if (!user) return jsonResponse({ detail: "用户不存在" }, 404);
    if (url.pathname.endsWith("/password") && method === "PUT") {
      const body = await readJson(request);
      const newPassword = String(body.new_password || "");
      if (newPassword.length < 8) return jsonResponse({ detail: "新密码至少需要 8 位" }, 400);
      managedPasswords.set(username, newPassword);
      return jsonResponse({ message: "用户密码修改成功" });
    }
    if (method === "PATCH" && !url.pathname.endsWith("/password")) {
      const body = await readJson(request);
      const displayName = String(body.display_name || "").trim();
      if (!displayName) return jsonResponse({ detail: "自定义名称不能为空" }, 400);
      user.display_name = displayName;
      return jsonResponse({ user: { ...user }, message: "用户信息已更新" });
    }
    if (method === "DELETE" && !url.pathname.endsWith("/password")) {
      ordinaryUsers.splice(ordinaryUsers.indexOf(user), 1);
      managedPasswords.delete(username);
      for (let index = privateMessages.length - 1; index >= 0; index -= 1) {
        if (privateMessages[index].sender_username === username || privateMessages[index].recipient_username === username) {
          privateMessages.splice(index, 1);
        }
      }
      return jsonResponse({ success: true, message: "用户已删除" });
    }
  }

  if (url.pathname === "/api/admin/users/password/reset" && method === "POST") {
    if (!activeUser || activeUser.role !== "admin") {
      return jsonResponse({ detail: "需要管理员权限" }, 403);
    }
    const body = await readJson(request);
    if (!String(body.username || "").trim()) {
      return jsonResponse({ detail: "请输入目标用户账号" }, 400);
    }
    return jsonResponse({ message: `已提交 ${body.username} 的密码重置请求` });
  }

  if (url.pathname === "/api/messages") {
    if (!activeUser) return jsonResponse({ detail: "请先登录" }, 401);
    if (method === "GET") {
      return jsonResponse({
        messages: privateMessages
          .filter((message) => message.sender_username === activeUser.username || message.recipient_username === activeUser.username)
          .map((message) => ({ ...message }))
      });
    }
    if (method === "POST") {
      const body = await readJson(request);
      const recipient = String(body.recipient || body.recipient_username || "").trim();
      const content = String(body.content || "").trim();
      if (!recipient || !content) return jsonResponse({ detail: "请填写收件人和消息内容" }, 400);
      if (content.length > 2000) return jsonResponse({ detail: "消息内容不能超过 2000 字" }, 400);
      const recipientUser = recipient === "admin"
        ? adminUser
        : ordinaryUsers.find((item) => item.username === recipient);
      if (!recipientUser) return jsonResponse({ detail: "收件人不存在" }, 404);
      if (activeUser.role === "admin" && recipientUser.role !== "user") {
        return jsonResponse({ detail: "管理员只能向普通用户发送私信" }, 400);
      }
      if (activeUser.role !== "admin" && recipientUser.username !== "admin") {
        return jsonResponse({ detail: "普通用户只能向管理员发送私信" }, 403);
      }
      const message = {
        id: `msg-${nextMessageId++}`,
        subject: String(body.subject || (activeUser.role === "admin" ? "管理员私信" : "用户与管理员私信")).trim(),
        sender: activeUser.display_name || activeUser.username,
        sender_username: activeUser.username,
        recipient: recipientUser.display_name || recipientUser.username,
        recipient_username: recipientUser.username,
        content,
        created_at: new Date().toISOString()
      };
      privateMessages.push(message);
      return jsonResponse({ message }, 201);
    }
  }

  if (url.pathname.startsWith("/api/")) {
    return jsonResponse({ detail: `Mock API 未实现：${method} ${url.pathname}` }, 404);
  }

  return null;
}

let installed = false;

export function installMock(enabled) {
  if (!enabled || installed) return;
  installed = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const requestUrl = input instanceof Request ? input.url : new URL(input, window.location.href).href;
    const request = new Request(requestUrl, init);
    const url = new URL(request.url, window.location.href);
    if (url.pathname.startsWith("/api/models")) {
      return nativeFetch(request);
    }
    if (url.port === "8080") {
      return jsonResponse({ detail: "Mock 模式已阻止连接 8080 端口" }, 503);
    }
    const response = await handleMockRequest(request, url);
    return response || nativeFetch(request);
  };
}
