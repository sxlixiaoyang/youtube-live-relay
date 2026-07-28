function formatTime(ts) {
  if (!ts) return "\u4ece\u672a";
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN");
}

async function checkServer() {
  const url = document.getElementById("serverUrl").value.trim();
  try {
    const r = await fetch(url + "/api/cookies", { method: "GET", signal: AbortSignal.timeout(3000) });
    const data = await r.json();
    document.getElementById("connStatus").textContent = "\u5df2\u8fde\u63a5";
    document.getElementById("connStatus").className = "value";
    document.getElementById("cookieCount").textContent = data.cookie_count || 0;
    return true;
  } catch (e) {
    document.getElementById("connStatus").textContent = "\u672a\u8fde\u63a5";
    document.getElementById("connStatus").className = "value error";
    document.getElementById("cookieCount").textContent = "-";
    return false;
  }
}

async function manualSend() {
  const btn = document.getElementById("btnSend");
  btn.disabled = true;
  btn.textContent = "\u53d1\u9001\u4e2d...";
  const resp = await chrome.runtime.sendMessage({ action: "sendCookies" });
  if (resp && resp.success) {
    btn.textContent = "\u53d1\u9001\u6210\u529f!";
    setTimeout(() => { btn.textContent = "\u7acb\u5373\u53d1\u9001Cookies"; btn.disabled = false; }, 2000);
  } else {
    btn.textContent = "\u53d1\u9001\u5931\u8d25";
    setTimeout(() => { btn.textContent = "\u7acb\u5373\u53d1\u9001Cookies"; btn.disabled = false; }, 2000);
  }
  checkServer();
}

async function updateStatus() {
  const resp = await chrome.runtime.sendMessage({ action: "getStatus" });
  if (resp) {
    document.getElementById("lastSent").textContent = formatTime(resp.lastSentTime);
  }
  checkServer();
}

document.getElementById("btnSend").addEventListener("click", manualSend);

updateStatus();
setInterval(updateStatus, 10000);
