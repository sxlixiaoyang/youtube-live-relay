const SERVER_URL = "http://localhost:8080/api/cookies";
let lastSentTime = 0;
const SEND_INTERVAL = 5 * 60 * 1000;

async function sendCookiesToServer() {
  try {
    const cookies = await chrome.cookies.getAll({ domain: ".youtube.com" });
    if (!cookies || cookies.length === 0) {
      console.log("[YT-Cookies] 未找到YouTube Cookies");
      return { success: false, message: "未找到YouTube Cookies" };
    }

    const cookieData = cookies.map(c => ({
      domain: c.domain,
      name: c.name,
      value: c.value,
      path: c.path,
      secure: c.secure,
      httpOnly: c.httpOnly,
      sameSite: c.sameSite,
      expirationDate: c.expirationDate || 0,
    }));

    const response = await fetch(SERVER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookies: cookieData, source: "chrome-extension" }),
    });

    const result = await response.json();
    if (result.success) {
      console.log(`[YT-Cookies] 成功发送 ${cookies.length} 个Cookies到服务器`);
      lastSentTime = Date.now();
    } else {
      console.log("[YT-Cookies] 服务器处理失败:", result.message);
    }
    return result;
  } catch (e) {
    console.error("[YT-Cookies] 发送失败:", e);
    return { success: false, message: e.message };
  }
}

function isYoutubeUrl(url) {
  return url && (url.includes("youtube.com") || url.includes("youtu.be"));
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isYoutubeUrl(tab.url)) {
    console.log("[YT-Cookies] 检测到YouTube页面:", tab.url);
    const now = Date.now();
    if (now - lastSentTime > SEND_INTERVAL) {
      sendCookiesToServer();
    }
  }
});

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const tab = await chrome.tabs.get(activeInfo.tabId);
  if (isYoutubeUrl(tab.url)) {
    console.log("[YT-Cookies] 切换到YouTube标签页");
    const now = Date.now();
    if (now - lastSentTime > SEND_INTERVAL) {
      sendCookiesToServer();
    }
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "sendCookies") {
    sendCookiesToServer().then(result => {
      sendResponse(result);
    });
    return true;
  }
  if (message.action === "getStatus") {
    sendResponse({
      lastSentTime: lastSentTime,
      serverUrl: SERVER_URL,
    });
    return true;
  }
});

console.log("[YT-Cookies] YouTube Cookies Helper 已启动");
