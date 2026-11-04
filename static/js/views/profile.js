function setStatus(element, text, state = "") {
  element.textContent = text;
  element.className = `status${state ? ` ${state}` : ""}`;
}

export function mountProfileView(root, { user, api, onUserUpdated = () => {} }) {
  root.innerHTML = `
    <header class="topbar">
      <a class="brand" href="#home" data-route="home" aria-label="FusionLab 首页"><div class="brand-mark" aria-hidden="true"></div>Fusion<span>Lab</span></a>
      <div class="topbar-actions">
        <nav class="nav" aria-label="主导航">
          <a class="btn btn-outline" href="#dashboard" data-route="dashboard">我的实验</a>
          <a class="btn btn-outline" href="#message" data-route="message">私信</a>
          ${user.role === "admin" ? '<a class="btn btn-outline" href="#admin" data-route="admin">管理员后台</a>' : ""}
        </nav>
        <a class="profile-pill" href="#profile" data-route="profile" aria-label="个人中心" aria-current="page">
          <div class="avatar" data-user-avatar aria-hidden="true"></div>
          <span class="profile-tooltip" role="tooltip"><b data-user-name></b><span>账号（学号）：<span data-user-account>—</span></span><span data-user-role></span><button class="logout-button" type="button" data-logout>退出登录</button><span class="status logout-status" data-logout-status role="status" aria-live="polite"></span></span>
        </a>
      </div>
    </header>
    <main class="container view-container">
      <header class="page-head"><p class="eyebrow">ACCOUNT</p><h1>个人中心</h1><p>查看账号信息并管理自己的密码。</p></header>
      <div class="account-grid">
        <section class="account-card">
          <h2>账号信息</h2>
          <dl class="account-info">
            <div><dt>账号（学号）</dt><dd data-account="accountId"></dd></div>
            <div><dt>自定义名称</dt><dd>
              <form id="displayNameForm" class="account-edit-form">
                <div class="account-edit-controls">
                  <div class="field"><input id="displayName" type="text" autocomplete="nickname" required maxlength="40" aria-label="自定义名称"></div>
                  <button class="btn btn-primary" type="submit">保存名称</button>
                </div>
                <p class="status" id="displayNameStatus" role="status" aria-live="polite"></p>
              </form>
            </dd></div>
            <div><dt>角色</dt><dd data-account="role"></dd></div>
            <div><dt>注册时间</dt><dd data-account="registered"></dd></div>
          </dl>
        </section>
        <section class="account-card">
          <h2>修改我的密码</h2>
          <p class="view-description">此操作只修改当前登录账号的密码。</p>
          <form id="changePasswordForm">
            <div class="field"><label for="currentPassword">当前密码</label><input id="currentPassword" type="password" autocomplete="current-password" required></div>
            <div class="field"><label for="newPassword">新密码</label><input id="newPassword" type="password" minlength="8" autocomplete="new-password" required></div>
            <div class="field"><label for="confirmPassword">确认新密码</label><input id="confirmPassword" type="password" minlength="8" autocomplete="new-password" required></div>
            <button class="btn btn-primary" type="submit">更新密码</button>
            <p class="status" id="passwordStatus" role="status" aria-live="polite"></p>
          </form>
        </section>
      </div>
    </main>`;

  const accountId = user.account_id || user.student_id || (/^\d+$/.test(String(user.username || "")) ? user.username : "—");
  const displayName = user.display_name || user.nickname || user.username;
  root.querySelector("[data-user-avatar]").textContent = displayName.slice(0, 1).toUpperCase();
  root.querySelector("[data-user-name]").textContent = displayName;
  root.querySelector("[data-user-account]").textContent = accountId;
  root.querySelector("[data-user-role]").textContent = user.role_name || "Engineering Workspace";
  root.querySelector('[data-account="accountId"]').textContent = accountId;
  root.querySelector("#displayName").value = user.display_name || user.nickname || user.username || "";
  root.querySelector('[data-account="role"]').textContent = user.role_name || (user.role === "admin" ? "管理员" : "普通用户");
  const registeredAt = user.registered_at ? new Date(user.registered_at) : null;
  root.querySelector('[data-account="registered"]').textContent =
    registeredAt && !Number.isNaN(registeredAt.getTime()) ? registeredAt.toLocaleString("zh-CN") : "—";

  const displayNameForm = root.querySelector("#displayNameForm");
  const displayNameStatus = root.querySelector("#displayNameStatus");
  displayNameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const displayName = root.querySelector("#displayName").value.trim();
    if (!displayName) {
      setStatus(displayNameStatus, "自定义名称不能为空。", "error");
      return;
    }
    if (displayName === (user.display_name || user.nickname || user.username)) {
      setStatus(displayNameStatus, "自定义名称未修改。");
      return;
    }
    const button = displayNameForm.querySelector("button[type=submit]");
    button.disabled = true;
    setStatus(displayNameStatus, "正在保存自定义名称…", "loading");
    try {
      const result = await api.post("/api/users/me/display-name", { display_name: displayName });
      user.display_name = result.user?.display_name || result.display_name || displayName;
      root.querySelector("#displayName").value = user.display_name;
      onUserUpdated(user);
      setStatus(displayNameStatus, result.message || "自定义名称修改成功。", "success");
    } catch (error) {
      setStatus(displayNameStatus, `自定义名称修改失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });

  const form = root.querySelector("#changePasswordForm");
  const status = root.querySelector("#passwordStatus");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const newPassword = root.querySelector("#newPassword").value;
    if (newPassword !== root.querySelector("#confirmPassword").value) {
      setStatus(status, "两次输入的新密码不一致。", "error");
      return;
    }
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    setStatus(status, "正在提交密码修改…", "loading");
    try {
      const result = await api.post("/api/users/me/password", {
        current_password: root.querySelector("#currentPassword").value,
        new_password: newPassword
      });
      form.reset();
      setStatus(status, result.message || "密码修改成功。", "success");
    } catch (error) {
      setStatus(status, `密码修改失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });
}
