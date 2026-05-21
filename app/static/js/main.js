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
                if (setupModal) {
                    setupModal.style.display = "flex";
                    loadSetupInfo();
                }
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

// SETUP WIZARD LOGIC
let selectedSetupTier = null;

async function loadSetupInfo() {
    try {
        const res = await fetch("/api/setup-info", {
            headers: { "Authorization": "Bearer " + token }
        });
        if (res.ok) {
            const data = await res.json();
            const detectedRam = document.getElementById("detectedRam");
            const recommendedTier = document.getElementById("recommendedTier");
            
            if (detectedRam) detectedRam.innerText = data.ram_gb + " GB";
            if (recommendedTier) {
                recommendedTier.innerText = data.recommended_tier;
            }
            
            // Auto-select recommended tier
            selectSetupTier(data.recommended_tier);
        }
    } catch (e) {
        console.error("Failed to load setup info:", e);
    }
}

function selectSetupTier(tier) {
    selectedSetupTier = tier;
    
    const liteEl = document.getElementById("tierLite");
    const balancedEl = document.getElementById("tierBalanced");
    const highEl = document.getElementById("tierHigh");
    
    if (liteEl) {
        liteEl.style.borderColor = "#e2e8f0";
        liteEl.style.background = "white";
    }
    if (balancedEl) {
        balancedEl.style.borderColor = "#e2e8f0";
        balancedEl.style.background = "white";
    }
    if (highEl) {
        highEl.style.borderColor = "#e2e8f0";
        highEl.style.background = "white";
    }
    
    let target = null;
    if (tier === "Lite") target = liteEl;
    else if (tier === "Balanced") target = balancedEl;
    else if (tier === "High Accuracy") target = highEl;
    
    if (target) {
        target.style.borderColor = "var(--primary-green)";
        target.style.background = "rgba(46, 125, 50, 0.04)";
    }
}

function finishSetup() {
    if (!selectedSetupTier) {
        alert("Please select an AI tier to continue.");
        return;
    }
    
    const setupModal = document.getElementById("setupWizardModal");
    if (setupModal) setupModal.style.display = "none";
    
    openSettings();
    
    if (typeof selectSettingsTier === 'function') {
        selectSettingsTier(selectedSetupTier);
    }
}

window.selectSetupTier = selectSetupTier;
window.finishSetup = finishSetup;

// ── Admin Panel Functions ──
async function checkAdmin() {
    try {
        const res = await fetch("/me", {
            headers: { "Authorization": "Bearer " + token }
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.is_admin) {
            const adminBtn = document.getElementById("adminPanelBtn");
            if (adminBtn) adminBtn.style.display = "flex";
        }
        if (data.username) {
            const el = document.getElementById("topUserName");
            if (el) {
                el.textContent = "Welcome, " + data.username;
                el.style.display = "inline-block";
            }
        }
    } catch (e) { console.error("Error checking admin status:", e); }
}

async function openAdminModal() {
    const adminModal = document.getElementById("adminModal");
    if (adminModal) adminModal.style.display = "flex";
    switchAdminTab('docs');
    loadAdminStats();
}

function closeAdminModal() {
    const adminModal = document.getElementById("adminModal");
    if (adminModal) adminModal.style.display = "none";
}

function switchAdminTab(tab) {
    const isDocs = tab === 'docs';
    const paneDocs = document.getElementById("paneDocs");
    const paneUsers = document.getElementById("paneUsers");
    const tabDocs = document.getElementById("tabDocs");
    const tabUsers = document.getElementById("tabUsers");

    if (paneDocs) paneDocs.style.display = isDocs ? 'block' : 'none';
    if (paneUsers) paneUsers.style.display = isDocs ? 'none' : 'block';
    
    if (tabDocs) {
        tabDocs.style.background = isDocs ? '#e8f5e9' : 'transparent';
        tabDocs.style.color = isDocs ? 'var(--primary-green)' : '#64748b';
    }
    
    if (tabUsers) {
        tabUsers.style.background = !isDocs ? '#e8f5e9' : 'transparent';
        tabUsers.style.color = !isDocs ? 'var(--primary-green)' : '#64748b';
    }
    
    if (isDocs) loadDocumentList();
    else loadUserList();
}

async function loadAdminStats() {
    try {
        const res = await fetch("/admin/stats", { headers: { "Authorization": "Bearer " + token }});
        if (res.ok) {
            const data = await res.json();
            const statDocs = document.getElementById("statDocs");
            const statChunks = document.getElementById("statChunks");
            const statUsers = document.getElementById("statUsers");
            const statSize = document.getElementById("statSize");
            if (statDocs) statDocs.innerText = data.documents;
            if (statChunks) statChunks.innerText = data.total_chunks;
            if (statUsers) statUsers.innerText = data.users;
            if (statSize) statSize.innerText = data.db_size_mb + "MB";
        }
    } catch (e) {}
}

let allDocs = [];
async function loadDocumentList() {
    const list = document.getElementById("docList");
    if (!list) return;
    list.innerHTML = "Loading...";
    try {
        const res = await fetch("/admin/documents", {
            headers: { "Authorization": "Bearer " + token }
        });
        if (res.ok) {
            const data = await res.json();
            allDocs = data.documents || [];
            renderDocs(allDocs);
        } else {
            list.innerHTML = "Failed to load documents.";
        }
    } catch (e) { list.innerHTML = "Error loading documents."; }
}

function renderDocs(docs) {
    const list = document.getElementById("docList");
    if (!list) return;
    list.innerHTML = "";
    if (docs.length === 0) {
        list.innerHTML = "<p style='color: #666; font-size: 14px; text-align:center; padding: 20px;'>No documents found.</p>";
        return;
    }
    docs.forEach(doc => {
        const div = document.createElement("div");
        div.style = "display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #eee;";
        div.innerHTML = `
            <div style="flex: 1; min-width: 0; padding-right: 15px;">
                <div style="font-weight: 600; font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${doc.filename}</div>
                <div style="font-size: 10.5px; color: #888;">Chunks: ${doc.chunk_count} • ${new Date(doc.created_at).toLocaleDateString()}</div>
            </div>
            <button onclick="deleteDoc(${doc.id})" style="background: #fee2e2; color: #ef4444; border: none; padding: 6px 12px; border-radius: 8px; font-size: 11px; cursor: pointer; font-weight: 700; flex-shrink: 0;">Delete</button>
        `;
        list.appendChild(div);
    });
}

function filterDocs() {
    const searchEl = document.getElementById("docSearch");
    if (!searchEl) return;
    const q = searchEl.value.toLowerCase();
    const filtered = allDocs.filter(d => d.filename.toLowerCase().includes(q));
    renderDocs(filtered);
}

async function loadUserList() {
    const list = document.getElementById("userList");
    if (!list) return;
    list.innerHTML = "Loading...";
    try {
        const res = await fetch("/admin/users", { headers: { "Authorization": "Bearer " + token }});
        if (res.ok) {
            const data = await res.json();
            list.innerHTML = "";
            data.users.forEach(u => {
                const div = document.createElement("div");
                div.style = "display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #eee;";
                div.innerHTML = `
                    <div>
                        <div style="font-weight: 600; font-size: 13.5px;">${u.username} ${u.is_admin ? '<span style="color:var(--primary-green); font-size:10px;">(Admin)</span>' : ''}</div>
                        <div style="font-size: 10.5px; color: #888;">Joined: ${new Date(u.created_at).toLocaleDateString()}</div>
                    </div>
                    <button onclick="resetUserPwd(${u.id}, '${u.username}')" style="background: #f1f5f9; color: #64748b; border: none; padding: 6px 12px; border-radius: 8px; font-size: 11px; cursor: pointer; font-weight: 700;">Reset Pwd</button>
                `;
                list.appendChild(div);
            });
        } else {
            list.innerHTML = "Failed to load users.";
        }
    } catch (e) { list.innerHTML = "Error loading users."; }
}

let activeResetUserId = null;
let activeResetUsername = "";

function resetUserPwd(id, username) {
    activeResetUserId = id;
    activeResetUsername = username;
    const titleEl = document.getElementById("pwdResetTitle");
    const inputEl = document.getElementById("newPwdInput");
    const modalEl = document.getElementById("pwdResetModal");
    if (titleEl) titleEl.innerText = `Reset Password for ${username}`;
    if (inputEl) inputEl.value = "";
    if (modalEl) modalEl.style.display = "flex";
}

function closePwdModal() {
    const modalEl = document.getElementById("pwdResetModal");
    if (modalEl) modalEl.style.display = "none";
}

async function deleteDoc(id) {
    if (typeof showConfirm === 'function') {
        const confirmed = await showConfirm(
            "Delete Document?",
            "This will remove the PDF and its AI memory index permanently.",
            "Delete"
        );
        if (!confirmed) return;
    } else {
        if (!confirm("Are you sure you want to delete this document?")) return;
    }
    try {
        const res = await fetch(`/admin/documents/${id}`, {
            method: "DELETE",
            headers: { "Authorization": "Bearer " + token }
        });
        if (res.ok) {
            loadDocumentList();
            loadAdminStats();
            if (typeof showToast === 'function') showToast("Document deleted successfully");
        } else {
            const err = await res.json().catch(() => ({ detail: "Unknown error" }));
            if (typeof showToast === 'function') showToast(err.detail || "Delete failed.", "error");
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast("Error deleting.", "error");
    }
}

function triggerUpload() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf";
    input.onchange = () => {
        const file = input.files[0];
        if (!file) return;

        const statusDiv = document.getElementById("uploadStatus");
        const bar = document.getElementById("uploadBar");
        const percentText = document.getElementById("uploadPercent");
        const nameText = document.getElementById("uploadFileName");
        const hint = document.getElementById("ingestHint");

        if (nameText) nameText.innerText = file.name;
        if (statusDiv) statusDiv.style.display = "block";
        if (bar) {
            bar.style.width = "0%";
            bar.style.background = "var(--primary-green)";
        }
        if (percentText) percentText.innerText = "0%";
        if (hint) hint.innerText = "Uploading to server...";

        const formData = new FormData();
        formData.append("file", file);

        const xhr = new XMLHttpRequest();
        
        // Track Upload Progress
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                if (bar) bar.style.width = percent + "%";
                if (percentText) percentText.innerText = percent + "%";
                if (percent === 100 && hint) {
                    hint.innerText = "Processing & Indexing for AI... (Almost there)";
                    if (bar) bar.style.background = "#fbbf24"; // Amber during processing
                }
            }
        };

        xhr.onload = () => {
            if (statusDiv) statusDiv.style.display = "none";
            if (bar) bar.style.background = "var(--primary-green)";
            if (xhr.status === 200) {
                loadDocumentList();
                loadAdminStats();
                if (typeof showToast === 'function') showToast("Document uploaded and indexed!");
            } else {
                let msg = "Upload failed";
                try {
                    const res = JSON.parse(xhr.responseText);
                    msg = res.detail || msg;
                } catch(e) {}
                if (typeof showToast === 'function') showToast(msg, "error");
            }
        };

        xhr.onerror = () => {
            if (statusDiv) statusDiv.style.display = "none";
            if (typeof showToast === 'function') showToast("Network error during upload.", "error");
        };

        xhr.open("POST", "/admin/upload-pdf");
        xhr.setRequestHeader("Authorization", "Bearer " + token);
        xhr.send(formData);
    };
    input.click();
}

function findDoctors() {
    if (!navigator.onLine) {
        alert("Internet connection required to find nearby doctors.");
        return;
    }
    if (!navigator.geolocation) {
        alert("Geolocation is not supported by your browser.");
        return;
    }
    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            const query = encodeURIComponent("doctor hospital clinic");
            const url = `https://www.google.com/maps/search/${query}/@${lat},${lon},14z`;
            window.open(url, "_blank");
            closeSidebar();
        },
        (error) => {
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    alert("Location permission required to find nearby doctors.");
                    break;
                case error.POSITION_UNAVAILABLE:
                    alert("Location information is unavailable.");
                    break;
                case error.TIMEOUT:
                    alert("The request to get user location timed out.");
                    break;
                default:
                    alert("An unknown error occurred while getting location.");
                    break;
            }
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

// Bind password confirm button
document.addEventListener("DOMContentLoaded", () => {
    const pwdConfirmBtn = document.getElementById("pwdConfirmBtn");
    if (pwdConfirmBtn) {
        pwdConfirmBtn.onclick = async () => {
            const newPwdInput = document.getElementById("newPwdInput");
            if (!newPwdInput) return;
            const newPwd = newPwdInput.value.trim();
            if (!newPwd) {
                if (typeof showToast === 'function') showToast("Please enter a password", "error");
                return;
            }
            
            try {
                const res = await fetch(`/admin/users/${activeResetUserId}/reset-password`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
                    body: JSON.stringify({ new_password: newPwd })
                });
                if (res.ok) {
                    if (typeof showToast === 'function') showToast(`Password for ${activeResetUsername} reset successfully!`);
                    closePwdModal();
                } else {
                    if (typeof showToast === 'function') showToast("Failed to update password.", "error");
                }
            } catch (e) {
                if (typeof showToast === 'function') showToast("Error connecting to server.", "error");
            }
        };
    }
});

async function checkUpdate() {
    try {
        const res = await fetch("/api/update/check", {
            headers: { "Authorization": "Bearer " + token }
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.available) {
            const modal = document.getElementById("updateModal");
            const versionText = document.getElementById("updateVersionText");
            const releaseNotes = document.getElementById("updateReleaseNotes");
            
            if (versionText) {
                versionText.innerText = `v${data.current_version} → v${data.latest_version}`;
            }
            if (releaseNotes) {
                releaseNotes.innerText = data.release_notes || "No release notes provided.";
            }
            if (modal) {
                modal.style.display = "flex";
            }
        }
    } catch (e) {
        console.error("Error checking for updates:", e);
    }
}

async function startUpdate() {
    try {
        const res = await fetch("/api/update/download", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token }
        });
        if (!res.ok) {
            const err = await res.json();
            if (typeof showToast === 'function') showToast(err.detail || "Failed to start update download.", "error");
            return;
        }
        
        const updateActions = document.getElementById("updateActions");
        const updateProgressContainer = document.getElementById("updateProgressContainer");
        if (updateActions) updateActions.style.display = "none";
        if (updateProgressContainer) updateProgressContainer.style.display = "block";
        
        pollUpdateProgress();
    } catch (e) {
        console.error("Error downloading update:", e);
        if (typeof showToast === 'function') showToast("Error contacting server.", "error");
    }
}

let updatePollInterval = null;
function pollUpdateProgress() {
    if (updatePollInterval) clearInterval(updatePollInterval);
    
    updatePollInterval = setInterval(async () => {
        try {
            const res = await fetch("/api/update/progress", {
                headers: { "Authorization": "Bearer " + token }
            });
            if (!res.ok) return;
            const data = await res.json();
            
            const updatePercent = document.getElementById("updatePercent");
            const updateBar = document.getElementById("updateBar");
            const updateStatusText = document.getElementById("updateStatusText");
            
            if (data.status === "error") {
                clearInterval(updatePollInterval);
                if (updateStatusText) updateStatusText.innerText = "Download failed!";
                if (updateStatusText) {
                    updateStatusText.style.color = "red";
                }
                if (typeof showToast === 'function') showToast("Update download failed.", "error");
                return;
            }
            
            const progress = data.progress || 0;
            if (updatePercent) updatePercent.innerText = progress + "%";
            if (updateBar) updateBar.style.width = progress + "%";
            
            if (progress >= 100) {
                clearInterval(updatePollInterval);
                if (updateStatusText) updateStatusText.innerText = "Applying update...";
                setTimeout(applyUpdate, 1500);
            }
        } catch (e) {
            console.error("Error polling update progress:", e);
        }
    }, 1000);
}

async function applyUpdate() {
    try {
        const res = await fetch("/api/update/apply", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token }
        });
        if (!res.ok) {
            const err = await res.json();
            if (typeof showToast === 'function') showToast(err.detail || "Failed to apply update.", "error");
        }
    } catch (e) {
        console.error("Error applying update:", e);
    }
}

async function checkUpdateManual() {
    if (typeof showToast === 'function') showToast("Checking for updates...");
    try {
        const res = await fetch("/api/update/check", {
            headers: { "Authorization": "Bearer " + token }
        });
        if (!res.ok) {
            if (typeof showToast === 'function') showToast("Could not reach update server.", "error");
            return;
        }
        const data = await res.json();
        if (data.available) {
            const modal = document.getElementById("updateModal");
            const versionText = document.getElementById("updateVersionText");
            const releaseNotes = document.getElementById("updateReleaseNotes");
            
            if (versionText) {
                versionText.innerText = `v${data.current_version} → v${data.latest_version}`;
            }
            if (releaseNotes) {
                releaseNotes.innerText = data.release_notes || "No release notes provided.";
            }
            if (modal) {
                modal.style.display = "flex";
            }
        } else {
            if (typeof showToast === 'function') showToast("You are on the latest version! (v" + (data.current_version || "2.0.0") + ")");
        }
    } catch (e) {
        console.error("Error checking for updates:", e);
        if (typeof showToast === 'function') showToast("Error connecting to server.", "error");
    }
}

// Bind to window object for inline HTML event access
window.checkAdmin = checkAdmin;
window.openAdminModal = openAdminModal;
window.closeAdminModal = closeAdminModal;
window.switchAdminTab = switchAdminTab;
window.loadAdminStats = loadAdminStats;
window.loadDocumentList = loadDocumentList;
window.renderDocs = renderDocs;
window.filterDocs = filterDocs;
window.loadUserList = loadUserList;
window.resetUserPwd = resetUserPwd;
window.closePwdModal = closePwdModal;
window.deleteDoc = deleteDoc;
window.triggerUpload = triggerUpload;
window.findDoctors = findDoctors;
window.checkUpdate = checkUpdate;
window.startUpdate = startUpdate;
window.applyUpdate = applyUpdate;
window.checkUpdateManual = checkUpdateManual;

// Start App
init();
