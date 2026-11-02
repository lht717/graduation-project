function formatDate(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN");
}

function messageSender(message) {
  return message.sender_username || message.sender || "未知发送人";
}

function messageRecipient(message) {
  return message.recipient_username || message.recipient || "未知接收人";
}

export async function mountMessageView(root, { user, api }) {
  root.innerHTML = `
    <header class="topbar">
      <a class="brand" href="#home" data-route="home" aria-label="FusionLab 首页"><div class="brand-mark" aria-hidden="true"></div>Fusion<span>Lab</span></a>
      <div class="topbar-actions">
        <nav class="nav" aria-label="主导航">
          <a href="#dashboard" data-route="dashboard">我的实验</a>
          <a class="btn btn-outline" href="#message" data-route="message" aria-current="page">私信</a>
          ${user.role === "admin" ? '<a class="btn btn-outline" href="#admin" data-route="admin">管理员后台</a>' : ""}
        </nav>
        <a class="profile-pill" href="#profile" data-route="profile" aria-label="个人中心">
          <div class="avatar" data-user-avatar aria-hidden="true"></div>
          <span class="profile-tooltip" role="tooltip"><b data-user-name></b><span>账号（学号）：<span data-user-account>—</span></span><span data-user-role></span><button class="logout-button" type="button" data-logout>退出登录</button><span class="status logout-status" data-logout-status role="status" aria-live="polite"></span></span>
        </a>
      </div>
    </header>
    <main class="container view-container">
      <header class="page-head"><p class="eyebrow">MESSAGES</p><h1>私信</h1><p>查看私信列表和消息收发信息。</p></header>
      <p class="status loading" id="messagesStatus" role="status" aria-live="polite">正在加载私信…</p>
      <section class="message-layout">
        <aside class="account-card">
          <div class="message-list-head"><h2>收件箱</h2><button class="btn btn-outline" id="refreshMessages">刷新</button></div>
          <div id="messageList" class="message-list"></div>
        </aside>
        <section class="account-card message-detail" aria-live="polite">
          <header class="message-conversation-head"><h2 id="messageTitle">选择一条私信</h2><p id="messageDate" class="view-description"></p></header>
          <div id="messageBody" class="message-body" aria-label="聊天记录">从左侧选择对话，查看消息内容。</div>
          <form id="replyForm" class="message-reply hidden">
            <label class="sr-only" for="replyContent">发送消息</label>
            <textarea id="replyContent" rows="2" maxlength="2000" required placeholder="输入要发送给管理员的消息"></textarea>
            <div class="message-reply-actions"><p class="status" id="replyStatus" role="status" aria-live="polite"></p><button class="btn btn-primary" type="submit">发送</button></div>
          </form>
        </section>
      </section>
    </main>`;

  const displayName = user.display_name || user.nickname || user.username;
  root.querySelector("[data-user-avatar]").textContent = displayName.slice(0, 1).toUpperCase();
  root.querySelector("[data-user-name]").textContent = displayName;
  const accountId = user.account_id || user.student_id || (/^\d+$/.test(String(user.username || "")) ? user.username : "—");
  root.querySelector("[data-user-account]").textContent = accountId;
  root.querySelector("[data-user-role]").textContent = user.role_name || "Engineering Workspace";

  const list = root.querySelector("#messageList");
  const status = root.querySelector("#messagesStatus");
  const body = root.querySelector("#messageBody");
  const replyForm = root.querySelector("#replyForm");
  const replyStatus = root.querySelector("#replyStatus");
  const currentUsername = user.username;
  let threads = [];
  let selectedThread = null;

  function getCounterpart(message) {
    const sender = messageSender(message);
    const recipient = messageRecipient(message);
    if (user.role !== "admin" && (sender === "admin" || sender === "管理员" || recipient === "admin")) return "admin";
    return sender === currentUsername ? recipient : sender;
  }

  function renderThread(thread) {
    selectedThread = thread;
    root.querySelector("#messageTitle").textContent = thread.label;
    root.querySelector("#messageDate").textContent = thread.messages.length
      ? formatDate(thread.messages[thread.messages.length - 1].created_at || thread.messages[thread.messages.length - 1].timestamp)
      : "与管理员的私信对话";
    root.querySelector("#messageSender").textContent = thread.label;
    root.querySelector("#messageRecipient").textContent = user.display_name || user.nickname || user.username;
    body.replaceChildren();
    if (!thread.messages.length) {
      body.textContent = thread.key === "admin" ? "暂无消息。你可以在下方给管理员发送私信。" : "暂无消息。";
    } else {
      thread.messages.forEach((message) => {
        const entry = document.createElement("article");
        entry.className = "message-entry";
        const senderUsername = messageSender(message);
        const isOwnMessage = senderUsername === currentUsername ||
          senderUsername === (user.display_name || user.nickname);
        entry.classList.toggle("message-entry-own", isOwnMessage);
        const heading = document.createElement("div");
        heading.className = "message-entry-meta";
        const senderName = isOwnMessage
          ? (user.display_name || user.nickname || currentUsername)
          : (message.sender_display_name || message.sender_name ||
            (senderUsername === "admin" ? "管理员" : message.sender || senderUsername));
        const sender = document.createElement("strong");
        sender.textContent = senderName;
        heading.append(sender);
        const content = document.createElement("div");
        content.className = "message-bubble";
        content.textContent = message.content || message.body || "（无消息内容）";
        const time = document.createElement("time");
        time.className = "message-entry-time";
        time.textContent = formatDate(message.created_at || message.timestamp);
        entry.append(heading, content, time);
        body.append(entry);
      });
    }
    body.scrollTop = body.scrollHeight;
    replyForm.classList.remove("hidden");
    replyForm.querySelector("#replyContent").placeholder = thread.key === "admin"
      ? "输入要发送给管理员的消息"
      : `输入要发送给 ${thread.label} 的消息`;
    setReplyStatus("");
    list.querySelectorAll("button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.threadKey === thread.key));
    });
  }

  function setReplyStatus(message, state = "") {
    replyStatus.textContent = message;
    replyStatus.className = `status${state ? ` ${state}` : ""}`;
  }

  function renderThreads() {
    list.replaceChildren();
    threads.forEach((thread) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "message-list-item";
      button.dataset.threadKey = thread.key;
      const heading = document.createElement("strong");
      heading.textContent = thread.label;
      const preview = document.createElement("span");
      preview.textContent = thread.messages.length
        ? thread.messages[thread.messages.length - 1].content || thread.messages[thread.messages.length - 1].body || "（无消息内容）"
        : "点击此处给管理员发送私信";
      button.append(heading, preview);
      button.addEventListener("click", () => renderThread(thread));
      list.append(button);
    });
  }

  async function loadMessages(preferredKey = selectedThread?.key) {
    status.textContent = "正在加载私信…";
    status.className = "status loading";
    list.replaceChildren();
    try {
      const result = await api.get("/api/messages");
      if (!Array.isArray(result.messages)) throw new Error("私信列表格式不正确");
      const grouped = new Map();
      result.messages.forEach((message) => {
        const key = getCounterpart(message);
        if (!grouped.has(key)) {
          grouped.set(key, {
            key,
            label: key === "admin" ? "管理员" : key,
            messages: []
          });
        }
        grouped.get(key).messages.push(message);
      });
      if (user.role !== "admin" && !grouped.has("admin")) {
        grouped.set("admin", { key: "admin", label: "管理员", messages: [] });
      }
      threads = [...grouped.values()];
      threads.forEach((thread) => thread.messages.sort((a, b) =>
        new Date(a.created_at || a.timestamp || 0) - new Date(b.created_at || b.timestamp || 0)
      ));
      threads.sort((a, b) => {
        if (a.key === "admin") return -1;
        if (b.key === "admin") return 1;
        const aDate = a.messages.at(-1)?.created_at || a.messages.at(-1)?.timestamp || "";
        const bDate = b.messages.at(-1)?.created_at || b.messages.at(-1)?.timestamp || "";
        return new Date(bDate) - new Date(aDate);
      });
      renderThreads();
      const activeThread = threads.find((thread) => thread.key === preferredKey) || threads[0];
      if (activeThread) renderThread(activeThread);
      else {
        root.querySelector("#messageTitle").textContent = "暂无私信";
        body.textContent = "当前没有私信。";
        replyForm.classList.add("hidden");
      }
      status.textContent = `私信加载成功，共 ${threads.length} 个对话。`;
      status.className = "status success";
    } catch (error) {
      status.textContent = `私信加载失败：${error.message}`;
      status.className = "status error";
      list.textContent = "无法加载私信，请稍后重试。";
    }
  }

  replyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedThread) return;
    const content = root.querySelector("#replyContent").value.trim();
    if (!content) {
      setReplyStatus("请输入消息内容。", "error");
      return;
    }
    const button = replyForm.querySelector('button[type="submit"]');
    button.disabled = true;
    setReplyStatus("正在发送…", "loading");
    try {
      await api.post("/api/messages", {
        recipient: selectedThread.key,
        subject: selectedThread.key === "admin" ? "用户与管理员私信" : `私信：${selectedThread.label}`,
        content
      });
      root.querySelector("#replyContent").value = "";
      setReplyStatus("消息发送成功。", "success");
      await loadMessages(selectedThread.key);
    } catch (error) {
      setReplyStatus(`消息发送失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });

  root.querySelector("#refreshMessages").addEventListener("click", () => loadMessages());
  await loadMessages();
}
