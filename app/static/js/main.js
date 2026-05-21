/**
 * ══════════════════════════════════════════════════════════════════════════════
 * HEALTH ASSIST - CORE STABILITY LAYER
 * ══════════════════════════════════════════════════════════════════════════════
 */

// 1. CORE UI FUNCTIONS (PRIORITY LOAD)
function toggleSidebar() {
    const s = document.getElementById("sidebar");
    const o = document.getElementById("overlay");
    if (!s || !o) {
        console.warn("Sidebar or Overlay element missing from DOM");
        return;
    }
    const isOpen = s.classList.contains("open");
    if (isOpen) {
        s.classList.remove("open");
        o.classList.remove("show");
    } else {
        s.classList.add("open");
        o.classList.add("show");
    }
}

function closeSidebar() {
    const s = document.getElementById("sidebar");
    const o = document.getElementById("overlay");
    if (s) s.classList.remove("open");
    if (o) o.classList.remove("show");
}

async function loadConversationList() {
    const listDiv = document.getElementById("convList");
    if (!listDiv) {
        console.error("Critical Error: Conversation list container (#convList) not found.");
        return;
    }

    const authToken = localStorage.getItem("token");
    if (!authToken) return;

    try {
        const res = await fetch("/conversations", {
            headers: { "Authorization": "Bearer " + authToken }
        });
        if (!res.ok) throw new Error("Failed to fetch conversations");
        
        const data = await res.json();
        const conversations = data.conversations || [];

        // Reset list with Section Label
        listDiv.innerHTML = '<div class="sb-section-label">Recent</div>';

        if (conversations.length === 0) {
            const empty = document.createElement("div");
            empty.style.cssText = "color:var(--sb-text-muted); font-size:12px; padding:8px 14px;";
            empty.textContent = "No conversations yet";
            listDiv.appendChild(empty);
            return;
        }

        conversations.forEach(conv => {
            const wrapper = document.createElement("div");
            wrapper.className = "conv-item-wrapper" + (conv.id === currentConversationId ? " active" : "");

            const btn = document.createElement("button");
            btn.className = "conv-item";
            btn.textContent = conv.title || "New conversation";
            btn.title = conv.title || "New conversation";
            btn.onclick = (e) => {
                const target = e.currentTarget.parentElement;
                if (target) {
                    target.classList.add("btn-pop");
                    setTimeout(() => target.classList.remove("btn-pop"), 300);
                }
                switchConversation(conv.id);
            };

            const delBtn = document.createElement("button");
            delBtn.className = "conv-delete-btn";
            delBtn.innerHTML = "🗑";
            delBtn.title = "Delete";
            delBtn.onclick = (e) => {
                e.stopPropagation();
                deleteConversation(conv.id);
            };

            wrapper.appendChild(btn);
            wrapper.appendChild(delBtn);
            listDiv.appendChild(wrapper);
        });
    } catch (e) {
        console.error("Error loading conversation list:", e);
    }
}

// 2. GLOBAL STATE & SELECTORS
const token = localStorage.getItem("token");
if (!token) window.location.replace(window.location.origin + "/");

let currentConversationId = null;
let abortController = null;
let hasActiveModel = false;
let modelPollInterval = null;
let updatePollInterval = null;

const chatDiv = document.getElementById("chat");
const questionInput = document.getElementById("question");
const sendBtn = document.getElementById("sendBtn");

// 3. TOAST NOTIFICATIONS
function showToast(message, type = 'success') {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? '✅' : '❌';
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = "toastOut 0.3s forwards";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 4. CHAT LOGIC
function parseMarkdown(text) {
    if (!text) return "";
    
    // Escape HTML first to prevent XSS
    let html = text.replace(/&/g, '&amp;')
                   .replace(/</g, '&lt;')
                   .replace(/>/g, '&gt;');
                   
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Italics: *text*
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    // Lists: - item
    html = html.replace(/^- (.*)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    
    // Headers: ### Header
    html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.*)$/gm, '<h2>$1</h2>');
    
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    
    return html;
}

function addMessage(content, sender) {
    if (!chatDiv) return;
    const div = document.createElement("div");
    div.className = `message ${sender}`;
    
    if (sender === "user") {
        // Just plain text for user
        div.innerText = content;
    } else {
        // Parse markdown for bot to show beautiful citations
        div.innerHTML = parseMarkdown(content);
    }
    
    if (sender === "bot") {
        const lower = content.toLowerCase();
        if (lower.includes("find doctors") || lower.includes("find a clinic") || lower.includes("nearest hospital")) {
            const btn = document.createElement("button");
            btn.innerText = "📍 Find Nearby Doctors";
            btn.style = "display: block; margin-top: 10px; padding: 10px 20px; background: white; color: var(--primary-green); border: 2px solid var(--primary-green); border-radius: 20px; font-weight: 700; cursor: pointer; font-size: 13px; transition: 0.2s;";
            btn.onclick = () => findDoctors();
            btn.onmouseover = () => { btn.style.background = "var(--primary-green)"; btn.style.color = "white"; };
            btn.onmouseout = () => { btn.style.background = "white"; btn.style.color = "var(--primary-green)"; };
            div.appendChild(btn);
        }
    }

    chatDiv.appendChild(div);
    chatDiv.scrollTop = chatDiv.scrollHeight;
}

async function switchConversation(convId) {
    if (convId === currentConversationId) { closeSidebar(); return; }
    currentConversationId = convId;
    if (chatDiv) chatDiv.innerHTML = "";

    try {
        const res = await fetch(`/messages/${convId}`, {
            headers: { "Authorization": "Bearer " + token }
        });
        const data = await res.json();
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(m => addMessage(m.content, m.sender));
        } else {
            addMessage("Hello! I am Health Assist. How can I help you today?", "bot");
        }
    } catch (e) {
        console.error("Error loading messages:", e);
        addMessage("Could not load messages for this conversation.", "bot");
    }

    loadConversationList();
    closeSidebar();
}

async function createNewConversation() {
    if (chatDiv) chatDiv.innerHTML = "";
    currentConversationId = null;
    try {
        const res = await fetch("/conversations", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({ title: "" })
        });
        const data = await res.json();
        currentConversationId = data.conversation_id;
        addMessage("Hello! I am Health Assist. How can I help you today?", "bot");
        loadConversationList();
    } catch (e) { console.error("Error creating conversation:", e); }
}

async function sendMessage() {
    if (!questionInput || !sendBtn) return;
    const text = questionInput.value.trim();
    if (!text) return;

    if (!currentConversationId) await createNewConversation();

    addMessage(text, "user");
    questionInput.value = "";
    sendBtn.disabled = true;
    const stopBtn = document.getElementById("stopBtn");
    if (stopBtn) stopBtn.style.display = "block";

    const loading = document.createElement("div");
    loading.className = "message bot dots";
    loading.id = "loadingMsg";
    if (chatDiv) {
        chatDiv.appendChild(loading);
        chatDiv.scrollTop = chatDiv.scrollHeight;
    }

    abortController = new AbortController();

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            signal: abortController.signal,
            body: JSON.stringify({
                question: text,
                conversation_id: currentConversationId
            })
        });
        const data = await res.json();
        document.getElementById("loadingMsg")?.remove();
        if (data.answer) {
            addMessage(data.answer, "bot");
        } else {
            addMessage("Error: " + JSON.stringify(data), "bot");
        }
        loadConversationList();
    } catch (e) {
        document.getElementById("loadingMsg")?.remove();
        if (e.name === 'AbortError') {
            addMessage("Response stopped by user.", "bot");
        } else {
            addMessage("Sorry, there was an error processing your request.", "bot");
        }
    } finally {
        if (sendBtn) sendBtn.disabled = false;
        if (stopBtn) stopBtn.style.display = "none";
        if (questionInput) questionInput.focus();
        abortController = null;
    }
}

// 5. UTILITY & MODAL HELPERS
function showConfirm(title, text, okLabel = "Confirm") {
    return new Promise((resolve) => {
        const modal = document.getElementById("confirmModal");
        const okBtn = document.getElementById("confirmOkBtn");
        const cancelBtn = document.getElementById("confirmCancelBtn");
        if (!modal || !okBtn || !cancelBtn) return resolve(false);
        
        document.getElementById("confirmTitle").innerText = title;
        document.getElementById("confirmText").innerText = text;
        okBtn.innerText = okLabel;
        modal.style.display = "flex";
        
        const cleanup = (val) => {
            modal.style.display = "none";
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            resolve(val);
        };
        okBtn.onclick = () => cleanup(true);
        cancelBtn.onclick = () => cleanup(false);
    });
}

async function deleteConversation(convId) {
    const confirmed = await showConfirm(
        "Delete Chat?", 
        "This will permanently delete all messages in this conversation.",
        "Delete"
    );
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/conversations/${convId}`, {
            method: "DELETE",
            headers: { "Authorization": "Bearer " + token }
        });
        if (!res.ok) {
            const err = await res.json();
            showToast(err.detail || "Could not delete", "error");
            return;
        }
        if (convId === currentConversationId) {
            currentConversationId = null;
            if (chatDiv) chatDiv.innerHTML = "";
            await createNewConversation();
        }
        loadConversationList();
        showToast("Conversation deleted");
    } catch (e) { console.error("Error deleting:", e); showToast("Delete failed", "error"); }
}

// 9. OTHER UTILITIES (Doctors, Logout, etc.)
function findDoctors() {
    if (!navigator.onLine) { alert("Internet connection required."); return; }
    if (!navigator.geolocation) { alert("Geolocation not supported."); return; }
    
    navigator.geolocation.getCurrentPosition((pos) => {
        const url = `https://www.google.com/maps/search/doctor+hospital+clinic/@${pos.coords.latitude},${pos.coords.longitude},14z`;
        window.open(url, "_blank");
        closeSidebar();
    }, (err) => alert("Location permission required."), { timeout: 10000 });
}

function handleLogout() {
    localStorage.removeItem("token");
    window.location.replace(window.location.origin + "/");
}

async function loadUserInfo() {
    const authToken = localStorage.getItem("token");
    if (!authToken) return;
    try {
        const res = await fetch("/me", {
            headers: { "Authorization": "Bearer " + authToken }
        });
        if (res.ok) {
            const data = await res.json();
            const username = data.username || "Ayushman Doley";
            
            let initials = "U";
            const parts = username.trim().split(/\s+/);
            if (parts.length >= 2) {
                initials = (parts[0][0] + parts[1][0]).toUpperCase();
            } else {
                initials = username.slice(0, 2).toUpperCase();
            }
            
            const tName = document.getElementById("triggerName");
            const pName = document.getElementById("popoverName");
            const tAvatar = document.getElementById("triggerAvatar");
            const pAvatar = document.getElementById("popoverAvatar");
            
            if (tName) tName.textContent = username;
            if (pName) pName.textContent = username;
            if (tAvatar) tAvatar.textContent = initials;
            if (pAvatar) pAvatar.textContent = initials;
            
            const role = data.is_admin ? "Super Admin" : "";
            const sub1 = document.getElementById("triggerSubtitle");
            const sub2 = document.getElementById("popoverSubtitle");
            if (sub1) {
                sub1.textContent = role;
                sub1.style.display = role ? "block" : "none";
            }
            if (sub2) {
                sub2.textContent = role;
                sub2.style.display = role ? "block" : "none";
            }
        }
    } catch (e) {
        console.error("Error fetching user info:", e);
    }
}

// 10. INITIALIZATION & EVENT LISTENERS
async function init() {
    console.log("Health Assist Initializing...");
    
    // Core Event Listeners
    const toggleBtn = document.getElementById("toggleSidebar");
    if (toggleBtn) toggleBtn.onclick = toggleSidebar;
    
    const overlayBtn = document.getElementById("overlay");
    if (overlayBtn) overlayBtn.onclick = closeSidebar;
    
    const newChatBtn = document.getElementById("newChatBtn");
    if (newChatBtn) {
        newChatBtn.onclick = async (e) => {
            e.currentTarget.classList.add("btn-pop");
            setTimeout(() => e.currentTarget.classList.remove("btn-pop"), 300);
            await createNewConversation();
            closeSidebar();
        };
    }

    const qInput = document.getElementById("question");
    if (qInput) {
        qInput.onkeypress = (e) => { if (e.key === "Enter") sendMessage(); };
    }
    
    const sBtn = document.getElementById("sendBtn");
    if (sBtn) sBtn.onclick = sendMessage;

    const stopBtn = document.getElementById("stopBtn");
    if (stopBtn) stopBtn.onclick = () => abortController?.abort();

    const profileBtn = document.getElementById("profileMainBtn");
    if (profileBtn) {
        profileBtn.onclick = (e) => {
            e.stopPropagation();
            const popover = document.getElementById("profilePopover");
            if (popover) {
                const isVisible = popover.style.display === "flex";
                popover.style.display = isVisible ? "none" : "flex";
            }
        };
    }

    document.addEventListener("click", (e) => {
        const popover = document.getElementById("profilePopover");
        const profileBtn = document.getElementById("profileMainBtn");
        if (popover && !popover.contains(e.target) && e.target !== profileBtn && !profileBtn.contains(e.target)) {
            popover.style.display = "none";
        }
    });

    loadUserInfo();

    // Load Initial Data
    if (typeof checkAdmin === 'function') checkAdmin();
    
    try {
        // Check models status
        const mRes = await fetch("/api/models", { headers: { "Authorization": "Bearer " + token }});
        if (mRes.ok) {
            const mData = await mRes.json();
            hasActiveModel = !!mData.active;
            if (!hasActiveModel) {
                const setupModal = document.getElementById("setupWizardModal");
                if (setupModal) setupModal.style.display = "flex";
            }
        }

        // Load conversation history
        const cRes = await fetch("/conversations", { headers: { "Authorization": "Bearer " + token }});
        const cData = await cRes.json();
        if (cData.conversations && cData.conversations.length > 0) {
            currentConversationId = cData.conversations[0].id;
            switchConversation(currentConversationId);
        } else {
            await createNewConversation();
        }
        loadConversationList();
    } catch (e) { console.error("Init error:", e); }
    
    // Check for updates delayed
    setTimeout(() => { if (typeof checkUpdate === 'function') checkUpdate(); }, 5000);
}

// Start App
init();
