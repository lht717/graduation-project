function setStatus(element, message, state = "") {
  element.textContent = message;
  element.className = `status${state ? ` ${state}` : ""}`;
}

export async function mountAdminView(root, { user, api, navigate }) {
  root.innerHTML = `
    <header class="topbar">
      <a class="brand" href="#home" data-route="home" aria-label="FusionLab 首页"><div class="brand-mark" aria-hidden="true"></div>Fusion<span>Lab</span></a>
      <div class="topbar-actions">
        <nav class="nav" aria-label="主导航">
          <a href="#dashboard" data-route="dashboard">我的实验</a>
          <a class="btn btn-outline" href="#message" data-route="message">私信</a>
          <a class="btn btn-outline" href="#admin" data-route="admin" aria-current="page">管理员后台</a>
        </nav>
        <a class="profile-pill" href="#profile" data-route="profile" aria-label="个人中心">
          <div class="avatar" data-user-avatar aria-hidden="true"></div>
          <span class="profile-tooltip" role="tooltip"><b data-user-name></b><span>账号（学号）：<span data-user-account>—</span></span><span data-user-role></span><button class="logout-button" type="button" data-logout>退出登录</button><span class="status logout-status" data-logout-status role="status" aria-live="polite"></span></span>
        </a>
      </div>
    </header>
    <main class="container view-container">
      <header class="page-head"><p class="eyebrow">ADMINISTRATION</p><h1>用户管理</h1><p>管理普通用户账号、名称和密码。</p></header>
      <section class="account-card admin-card">
        <div class="message-list-head"><h2>普通用户</h2><button class="btn btn-primary" id="showCreateUser" type="button">新增用户</button></div>
        <div class="admin-user-toolbar"><label class="sr-only" for="userSearch">搜索用户</label><input id="userSearch" type="search" placeholder="搜索账号或自定义名称"><button class="btn btn-outline" id="refreshUsers" type="button">刷新</button></div>
        <p class="status" id="usersStatus" role="status" aria-live="polite"></p>
        <div class="admin-table-wrap">
          <table class="admin-user-table">
            <thead><tr><th>账号（学号）</th><th>自定义名称</th><th>注册时间</th><th>操作</th></tr></thead>
            <tbody id="usersTableBody"></tbody>
          </table>
        </div>
      </section>
      <section class="account-card admin-card admin-user-form hidden" id="messagePanel">
        <h2 id="messageFormTitle">发送私信</h2>
        <form id="adminMessageForm">
          <div class="field"><label for="adminMessageContent">消息内容</label><textarea id="adminMessageContent" rows="4" maxlength="2000" required placeholder="输入要发送给用户的私信"></textarea></div>
          <div class="admin-form-actions"><button class="btn btn-primary" type="submit" id="sendAdminMessage">发送私信</button><button class="btn btn-outline" type="button" id="cancelAdminMessage">取消</button></div>
          <p class="status" id="adminMessageStatus" role="status" aria-live="polite"></p>
        </form>
      </section>
      <section class="account-card admin-card admin-user-form hidden" id="userFormPanel">
        <h2 id="userFormTitle">新增普通用户</h2>
        <form id="userForm">
          <div class="field"><label for="userAccount">账号（学号）</label><input id="userAccount" name="username" inputmode="numeric" pattern="[0-9]+" autocomplete="off" required></div>
          <div class="field"><label for="userDisplayName">自定义名称</label><input id="userDisplayName" name="display_name" maxlength="40" required></div>
          <div class="field" id="initialPasswordField"><label for="userPassword">初始密码</label><input id="userPassword" name="password" type="password" minlength="8" autocomplete="new-password" required></div>
          <div class="admin-form-actions"><button class="btn btn-primary" type="submit" id="saveUserButton">创建用户</button><button class="btn btn-outline" type="button" id="cancelUserForm">取消</button></div>
          <p class="status" id="userFormStatus" role="status" aria-live="polite"></p>
        </form>
      </section>
      <section class="account-card admin-card admin-user-form hidden" id="passwordPanel">
        <h2 id="passwordFormTitle">修改用户密码</h2>
        <form id="passwordForm">
          <div class="field"><label for="userNewPassword">新密码</label><input id="userNewPassword" type="password" minlength="8" autocomplete="new-password" required></div>
          <div class="field"><label for="userConfirmPassword">确认新密码</label><input id="userConfirmPassword" type="password" minlength="8" autocomplete="new-password" required></div>
          <div class="admin-form-actions"><button class="btn btn-primary" type="submit">确认修改</button><button class="btn btn-outline" type="button" id="cancelPasswordForm">取消</button></div>
          <p class="status" id="passwordFormStatus" role="status" aria-live="polite"></p>
        </form>
      </section>
    </main>`;

  const displayName = user.display_name || user.nickname || user.username;
  const accountId = user.account_id || user.student_id || (/^\d+$/.test(String(user.username || "")) ? user.username : "—");
  root.querySelector("[data-user-avatar]").textContent = displayName.slice(0, 1).toUpperCase();
  root.querySelector("[data-user-name]").textContent = displayName;
  root.querySelector("[data-user-account]").textContent = accountId;
  root.querySelector("[data-user-role]").textContent = user.role_name || "Engineering Workspace";

  const tableBody = root.querySelector("#usersTableBody");
  const usersStatus = root.querySelector("#usersStatus");
  const userFormPanel = root.querySelector("#userFormPanel");
  const userForm = root.querySelector("#userForm");
  const userFormStatus = root.querySelector("#userFormStatus");
  const passwordPanel = root.querySelector("#passwordPanel");
  const passwordForm = root.querySelector("#passwordForm");
  const passwordFormStatus = root.querySelector("#passwordFormStatus");
  const messagePanel = root.querySelector("#messagePanel");
  const adminMessageForm = root.querySelector("#adminMessageForm");
  const adminMessageStatus = root.querySelector("#adminMessageStatus");
  let users = [];
  let editingUsername = null;
  let passwordUsername = null;
  let messageUsername = null;

  function closeForms() {
    userFormPanel.classList.add("hidden");
    passwordPanel.classList.add("hidden");
    messagePanel.classList.add("hidden");
    editingUsername = null;
    passwordUsername = null;
    messageUsername = null;
  }

  function renderUsers() {
    const query = root.querySelector("#userSearch").value.trim().toLocaleLowerCase();
    const filteredUsers = users.filter((item) =>
      `${item.username} ${item.account_id || ""} ${item.display_name || ""}`.toLocaleLowerCase().includes(query)
    );
    tableBody.replaceChildren();
    if (!filteredUsers.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.className = "admin-empty";
      cell.textContent = users.length ? "没有匹配的用户" : "暂无普通用户";
      row.append(cell);
      tableBody.append(row);
      return;
    }

    filteredUsers.forEach((item) => {
      const row = document.createElement("tr");
      const accountCell = document.createElement("td");
      accountCell.textContent = item.account_id || item.student_id || item.username || "—";
      const displayCell = document.createElement("td");
      displayCell.textContent = item.display_name || item.nickname || "—";
      const registeredCell = document.createElement("td");
      const date = item.registered_at ? new Date(item.registered_at) : null;
      registeredCell.textContent = date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("zh-CN") : "—";
      const actionsCell = document.createElement("td");
      actionsCell.className = "admin-user-actions";
      [
        ["edit", "编辑"],
        ["message", "私信"],
        ["password", "改密码"],
        ["delete", "删除"]
      ].forEach(([action, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = action === "delete" ? "btn btn-danger" : "btn btn-outline";
        button.dataset.action = action;
        button.dataset.username = item.username;
        button.textContent = label;
        actionsCell.append(button);
      });
      row.append(accountCell, displayCell, registeredCell, actionsCell);
      tableBody.append(row);
    });
  }

  async function loadUsers() {
    setStatus(usersStatus, "正在加载用户…", "loading");
    tableBody.replaceChildren();
    try {
      const result = await api.get("/api/admin/users");
      if (!Array.isArray(result.users)) throw new Error("用户列表格式不正确");
      users = result.users.filter((item) => item.role !== "admin");
      renderUsers();
      setStatus(usersStatus, `加载成功，共 ${users.length} 位普通用户。`, "success");
    } catch (error) {
      users = [];
      renderUsers();
      setStatus(usersStatus, `用户列表加载失败：${error.message}`, "error");
    }
  }

  function openCreateForm() {
    closeForms();
    editingUsername = null;
    userForm.reset();
    root.querySelector("#userFormTitle").textContent = "新增普通用户";
    root.querySelector("#userAccount").readOnly = false;
    root.querySelector("#initialPasswordField").classList.remove("hidden");
    root.querySelector("#userPassword").required = true;
    root.querySelector("#saveUserButton").textContent = "创建用户";
    setStatus(userFormStatus, "");
    userFormPanel.classList.remove("hidden");
    userFormPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    root.querySelector("#userAccount").focus();
  }

  function openEditForm(item) {
    closeForms();
    editingUsername = item.username;
    userForm.reset();
    root.querySelector("#userFormTitle").textContent = `编辑用户：${item.username}`;
    root.querySelector("#userAccount").value = item.account_id || item.student_id || item.username;
    root.querySelector("#userAccount").readOnly = true;
    root.querySelector("#userDisplayName").value = item.display_name || item.nickname || "";
    root.querySelector("#initialPasswordField").classList.add("hidden");
    root.querySelector("#userPassword").required = false;
    root.querySelector("#saveUserButton").textContent = "保存修改";
    setStatus(userFormStatus, "");
    userFormPanel.classList.remove("hidden");
    userFormPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    root.querySelector("#userDisplayName").focus();
  }

  root.querySelector("#showCreateUser").addEventListener("click", openCreateForm);
  root.querySelector("#refreshUsers").addEventListener("click", loadUsers);
  root.querySelector("#userSearch").addEventListener("input", renderUsers);
  root.querySelector("#cancelUserForm").addEventListener("click", closeForms);
  root.querySelector("#cancelPasswordForm").addEventListener("click", closeForms);
  root.querySelector("#cancelAdminMessage").addEventListener("click", closeForms);

  tableBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const item = users.find((entry) => entry.username === button.dataset.username);
    if (!item) return;
    if (button.dataset.action === "edit") {
      openEditForm(item);
      return;
    }
    if (button.dataset.action === "password") {
      closeForms();
      passwordUsername = item.username;
      passwordForm.reset();
      root.querySelector("#passwordFormTitle").textContent = `修改用户密码：${item.username}`;
      setStatus(passwordFormStatus, "");
      passwordPanel.classList.remove("hidden");
      passwordPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      root.querySelector("#userNewPassword").focus();
      return;
    }
    if (button.dataset.action === "message") {
      closeForms();
      messageUsername = item.username;
      adminMessageForm.reset();
      root.querySelector("#messageFormTitle").textContent = `发送私信给：${item.display_name || item.username}`;
      setStatus(adminMessageStatus, "");
      messagePanel.classList.remove("hidden");
      messagePanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      root.querySelector("#adminMessageContent").focus();
      return;
    }
    if (button.dataset.action === "delete" && window.confirm(`确定删除普通用户“${item.username}”吗？此操作不可撤销。`)) {
      button.disabled = true;
      setStatus(usersStatus, `正在删除用户 ${item.username}…`, "loading");
      try {
        await api.remove(`/api/admin/users/${encodeURIComponent(item.username)}`);
        setStatus(usersStatus, `用户 ${item.username} 已删除。`, "success");
        await loadUsers();
      } catch (error) {
        button.disabled = false;
        setStatus(usersStatus, `删除失败：${error.message}`, "error");
      }
    }
  });

  userForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const account = root.querySelector("#userAccount").value.trim();
    const name = root.querySelector("#userDisplayName").value.trim();
    const button = root.querySelector("#saveUserButton");
    button.disabled = true;
    setStatus(userFormStatus, editingUsername ? "正在保存用户信息…" : "正在创建用户…", "loading");
    try {
      const successMessage = editingUsername ? "用户信息已更新。" : "用户创建成功。";
      if (editingUsername) {
        await api.patch(`/api/admin/users/${encodeURIComponent(editingUsername)}`, { display_name: name });
      } else {
        await api.post("/api/admin/users", {
          username: account,
          account_id: account,
          display_name: name,
          password: root.querySelector("#userPassword").value,
          role: "user"
        });
      }
      await loadUsers();
      if (usersStatus.classList.contains("success")) setStatus(usersStatus, successMessage, "success");
      userForm.reset();
      closeForms();
    } catch (error) {
      setStatus(userFormStatus, `操作失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });

  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const newPassword = root.querySelector("#userNewPassword").value;
    if (newPassword !== root.querySelector("#userConfirmPassword").value) {
      setStatus(passwordFormStatus, "两次输入的新密码不一致。", "error");
      return;
    }
    const button = passwordForm.querySelector('button[type="submit"]');
    button.disabled = true;
    setStatus(passwordFormStatus, "正在修改密码…", "loading");
    try {
      await api.put(`/api/admin/users/${encodeURIComponent(passwordUsername)}/password`, { new_password: newPassword });
      setStatus(usersStatus, `用户 ${passwordUsername} 密码修改成功。`, "success");
      passwordForm.reset();
      closeForms();
    } catch (error) {
      setStatus(passwordFormStatus, `修改密码失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });

  adminMessageForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = root.querySelector("#adminMessageContent").value.trim();
    if (!content || !messageUsername) {
      setStatus(adminMessageStatus, "请输入消息内容。", "error");
      return;
    }
    const button = root.querySelector("#sendAdminMessage");
    button.disabled = true;
    setStatus(adminMessageStatus, "正在发送私信…", "loading");
    try {
      await api.post("/api/messages", {
        recipient: messageUsername,
        subject: "管理员私信",
        content
      });
      adminMessageForm.reset();
      navigate("message");
    } catch (error) {
      setStatus(adminMessageStatus, `私信发送失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });

  await loadUsers();
}
