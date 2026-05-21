/**
 * ══════════════════════════════════════════════════════════════════════════════
 * HEALTH ASSIST - SETTINGS HUB MODULE
 * ══════════════════════════════════════════════════════════════════════════════
 */

// 1. SETTINGS HUB NAVIGATION
async function openSettings() {
    const modal = document.getElementById("settingsModal");
    if (modal) {
        modal.style.display = "flex";
        loadModels();
        loadDocumentList();
        
        if (typeof closeSidebar === 'function') closeSidebar();
    }
}

function closeSettings() {
    const modal = document.getElementById("settingsModal");
    if (modal) modal.style.display = "none";
}

function switchSettingsTab(tab, el) {
    document.querySelectorAll(".tab-pane").forEach(p => p.style.display = "none");
    const target = document.getElementById(`tab-${tab}`);
    if (target) target.style.display = "block";
    
    document.querySelectorAll(".settings-tab").forEach(t => t.classList.remove("active"));
    if (el) {
        el.classList.add("active");
        const title = document.getElementById("settingsTitle");
        if (title) title.innerText = el.innerText.replace(/[🤖📚👤]\s/, '');
    }
}

// 2. MODELS MANAGEMENT
const RECOMMENDED_MODELS = [
    { name: "tinyllama", desc: "Fast & Lightweight", ram: "1GB", speed: "Very Fast", size: "640MB", tier: "Lite" },
    { name: "phi3:mini", desc: "Microsoft Phi-3 Mini", ram: "4GB", speed: "Fast", size: "2.3GB", tier: "Balanced" },
    { name: "qwen2.5:3b", desc: "Qwen 2.5 3B", ram: "4GB+", speed: "Fast", size: "1.9GB", tier: "High Accuracy" },
    { name: "llama3:8b", desc: "Meta Llama 3 8B", ram: "8GB", speed: "Moderate", size: "4.7GB", tier: "Pro" },
    { name: "mistral:latest", desc: "Mistral 7B v0.3", ram: "8GB", speed: "Moderate", size: "4.1GB", tier: "Pro" },
    { name: "moondream:latest", desc: "Moondream 2 (Vision)", ram: "2GB", speed: "Fast", size: "829MB", tier: "Lite" }
];

const TIER_INFO = {
    'Lite': { 
        title: "Lite Mode", 
        desc: "Optimized for speed. Perfect for low-power devices or quick symptoms checks.", 
        ram: "1 GB+", 
        model: "TinyLlama", 
        id: "tinyllama",
        embed: "BGE-Small-V1.5 (Light)",
        reranker: "None (Fast Mode)"
    },
    'Balanced': { 
        title: "Balanced Mode", 
        desc: "The best all-rounder. Smart, reliable, and runs smoothly on most modern PCs.", 
        ram: "4 GB+", 
        model: "Phi-3 Mini", 
        id: "phi3:mini",
        embed: "BGE-Base-V1.5 (Balanced)",
        reranker: "BGE-Reranker-Base"
    },
    'High Accuracy': { 
        title: "Pro Mode", 
        desc: "Deep medical analysis. Best for complex reports and detailed health questions.", 
        ram: "8 GB+", 
        model: "Qwen 2.5 3B", 
        id: "qwen2.5:3b",
        embed: "BGE-Large-V1.5 (Precise)",
        reranker: "BGE-Reranker-Large"
    }
};

function selectSettingsTier(tier) {
    // 1. Update Visuals
    document.querySelectorAll(".tier-card").forEach(c => c.classList.remove("active"));
    const activeCard = document.getElementById(`tierCard-${tier.split(' ')[0]}`);
    if (activeCard) activeCard.classList.add("active");

    // 2. Update Details Panel
    const panel = document.getElementById("tierDetailsPanel");
    const info = TIER_INFO[tier];
    if (panel && info) {
        panel.style.display = "block";
        document.getElementById("tierDetailTitle").innerText = info.title;
        document.getElementById("tierDetailDesc").innerText = info.desc;
        document.getElementById("specRam").innerText = info.ram;
        document.getElementById("specModel").innerText = info.model;
        document.getElementById("specEmbed").innerText = info.embed;
        document.getElementById("specReranker").innerText = info.reranker;
        
        // 3. Update Button Action
        const btn = document.getElementById("tierDownloadBtn");
        btn.onclick = () => pullModel(info.id);
        
        // Check if already installed
        checkTierStatus(info.id);
    }
}

async function checkTierStatus(modelId) {
    try {
        const res = await fetch("/api/models", { headers: { "Authorization": "Bearer " + token }});
        const data = await res.json();
        const installed = data.models || [];
        const btn = document.getElementById("tierDownloadBtn");
        
        const isInstalled = installed.includes(modelId) || installed.includes(modelId + ":latest");
        if (isInstalled) {
            btn.innerText = "Already Installed ✓";
            btn.style.background = "#f1f5f9";
            btn.style.color = "#64748b";
            btn.disabled = true;
        } else {
            btn.innerText = "Download & Activate";
            btn.style.background = "var(--primary-green)";
            btn.style.color = "white";
            btn.disabled = false;
        }
    } catch(e) {}
}

async function loadModels() {
    try {
        const res = await fetch("/api/models", { headers: { "Authorization": "Bearer " + token }});
        if (!res.ok) return;
        const data = await res.json();
        
        hasActiveModel = !!data.active;
        const qInput = document.getElementById("question");
        const sBtn = document.getElementById("sendBtn");
        
        if (qInput && sBtn) {
            if (!hasActiveModel) {
                qInput.disabled = true;
                qInput.placeholder = "Please select a model from Settings first...";
                sBtn.disabled = true;
            } else {
                qInput.disabled = false;
                qInput.placeholder = "Ask me anything — symptoms, medications, or general questions...";
                sBtn.disabled = false;
            }
        }
        renderModels(data.models || [], data.active);
    } catch(e) { console.error("Error loading models:", e); }
}

function renderModels(installed, active) {
    const list = document.getElementById("modelsList");
    if (!list) return;
    list.innerHTML = "";
    
    if (installed.length === 0) {
        list.innerHTML = "<p style='color:#64748b; font-size:14px;'>No models installed.</p>";
    } else {
        installed.forEach(m => {
            const isActive = m === active;
            const div = document.createElement("div");
            div.style = `padding: 12px; border: 1px solid ${isActive ? 'var(--primary-green)' : '#e2e8f0'}; border-radius: 10px; background: ${isActive ? '#f0fdf4' : 'white'}; display: flex; justify-content: space-between; align-items: center;`;
            
            const btnHtml = isActive ? 
                `<span style="color: var(--primary-green); font-weight: 700; font-size: 13px;">Active ✓</span>` : 
                `<button onclick="setActiveModel('${m}')" style="background:var(--primary-green); color:white; border:none; padding:6px 12px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:600;">Select</button>`;
                
            div.innerHTML = `
                <div><strong style="font-size: 15px;">${m}</strong></div>
                <div style="display:flex; gap:10px; align-items:center;">
                    ${btnHtml}
                    <button onclick="deleteModel('${m}')" style="background:#fee2e2; color:#ef4444; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:600;" ${isActive ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : ''}>🗑</button>
                </div>
            `;
            list.appendChild(div);
        });
    }

    const recList = document.getElementById("recommendedModelsList");
    if (!recList) return;
    recList.innerHTML = "";
    RECOMMENDED_MODELS.forEach(m => {
        const isInstalled = installed.includes(m.name) || installed.includes(m.name + ":latest");
        const div = document.createElement("div");
        div.style = `padding: 12px; border: 1px solid #e2e8f0; border-radius: 10px; background: white;`;
        
        let btn = isInstalled ? 
            `<span style="color: #64748b; font-size: 12px; font-weight: 600;">Installed ✓</span>` : 
            `<button onclick="pullModel('${m.name}')" style="background:var(--primary-green); color:white; border:none; padding:6px 12px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:600;">Download</button>`;

        div.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div>
                    <strong style="font-size: 15px;">${m.name}</strong>
                    <div style="font-size: 12px; color: #64748b; margin-top: 2px;">${m.desc}</div>
                </div>
                ${btn}
            </div>
            <div style="display: flex; gap: 8px; font-size: 10px; color: #94a3b8; flex-wrap: wrap;">
                <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">RAM: ${m.ram}</span>
                <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">Size: ${m.size}</span>
                <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">Speed: ${m.speed}</span>
            </div>
        `;
        recList.appendChild(div);
    });
}

async function setActiveModel(modelName) {
    try {
        const res = await fetch("/api/models/active", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
            body: JSON.stringify({ model: modelName })
        });
        if (res.ok) {
            if (typeof showToast === 'function') showToast(`Active model set to ${modelName}`);
            loadModels();
        }
    } catch(e) { console.error("Error setting active model:", e); }
}

async function pullModel(modelName) {
    try {
        const res = await fetch("/api/models/pull", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
            body: JSON.stringify({ model: modelName })
        });
        if (res.ok) {
            if (typeof showToast === 'function') showToast("Download started!");
            startPollingProgress();
        } else {
            const data = await res.json();
            if (typeof showToast === 'function') showToast(data.detail || "Could not start download", "error");
        }
    } catch(e) { console.error("Error pulling model:", e); }
}

function startPollingProgress() {
    const container = document.getElementById("downloadProgressContainer");
    if (!container) return;
    container.style.display = "block";
    const bar = document.getElementById("downloadBar");
    if (bar) bar.style.background = "var(--primary-green)";
    
    if (modelPollInterval) clearInterval(modelPollInterval);
    
    modelPollInterval = setInterval(async () => {
        try {
            const res = await fetch("/api/models/progress", { headers: { "Authorization": "Bearer " + token }});
            const data = await res.json();
            
            if (data.status === "idle") {
                clearInterval(modelPollInterval);
                container.style.display = "none";
                return;
            }
            
            const nameEl = document.getElementById("downloadModelName");
            const percEl = document.getElementById("downloadPercent");
            const barEl = document.getElementById("downloadBar");
            const statsEl = document.getElementById("downloadStats");

            if (nameEl) nameEl.innerText = `Downloading ${data.model}...`;
            if (percEl) percEl.innerText = data.percent + "%";
            if (barEl) barEl.style.width = data.percent + "%";
            
            if (statsEl && data.downloaded && data.total) {
                let statsStr = `${data.downloaded} / ${data.total}`;
                if (data.speed) statsStr += ` • ${data.speed}`;
                statsEl.innerText = statsStr;
            }
            
            if (data.status === "success") {
                clearInterval(modelPollInterval);
                if (percEl) percEl.innerText = "Completed!";
                setTimeout(() => { container.style.display = "none"; loadModels(); }, 2000);
                if (typeof showToast === 'function') showToast(`${data.model} downloaded successfully!`);
            } else if (data.status === "failed") {
                clearInterval(modelPollInterval);
                if (barEl) barEl.style.background = "#ef4444";
                if (typeof showToast === 'function') showToast("Model download failed.", "error");
            }
        } catch(e) { console.error("Polling error:", e); }
    }, 1000);
}

async function cancelDownload() {
    try {
        const res = await fetch("/api/models/cancel", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token }
        });
        if (res.ok) {
            if (modelPollInterval) clearInterval(modelPollInterval);
            const container = document.getElementById("downloadProgressContainer");
            if (container) container.style.display = "none";
            if (typeof showToast === 'function') showToast("Download cancelled successfully.");
            loadModels();
        } else {
            const data = await res.json();
            if (typeof showToast === 'function') showToast(data.detail || "Could not cancel download", "error");
        }
    } catch(e) {
        console.error("Error cancelling download:", e);
    }
}

window.cancelDownload = cancelDownload;

// 3. DOCUMENT LOGIC (Knowledge Base)
async function loadDocumentList() {
    const list = document.getElementById("docListSettings") || document.getElementById("docList");
    if (!list) return;
    list.innerHTML = "Loading...";
    try {
        const res = await fetch("/admin/documents", { headers: { "Authorization": "Bearer " + token }});
        const data = await res.json();
        renderDocs(data.documents || []);
    } catch (e) { list.innerHTML = "Error loading documents."; }
}

function renderDocs(docs) {
    const list = document.getElementById("docListSettings") || document.getElementById("docList");
    if (!list) return;
    list.innerHTML = "";
    if (docs.length === 0) {
        list.innerHTML = "<p style='color: #666; font-size: 14px; text-align:center; padding: 20px;'>No documents found.</p>";
        return;
    }
    docs.forEach(doc => {
        const div = document.createElement("div");
        div.style = "display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #eee; background: white; border-radius: 8px; margin-bottom: 4px;";
        div.innerHTML = `
            <div style="flex: 1; min-width: 0; padding-right: 15px;">
                <div style="font-weight: 600; font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${doc.filename}</div>
                <div style="font-size: 10.5px; color: #888;">Chunks: ${doc.chunk_count}</div>
            </div>
            <button onclick="deleteDoc(${doc.id})" style="background: #fee2e2; color: #ef4444; border: none; padding: 6px 12px; border-radius: 8px; font-size: 11px; cursor: pointer; font-weight: 700;">Delete</button>
        `;
        list.appendChild(div);
    });
}

async function deleteDoc(id) {
    if (typeof showConfirm !== 'function') return;
    const confirmed = await showConfirm("Delete Document?", "This will remove the PDF and its AI memory index permanently.", "Delete");
    if (!confirmed) return;
    try {
        const res = await fetch(`/admin/documents/${id}`, { method: "DELETE", headers: { "Authorization": "Bearer " + token }});
        if (res.ok) {
            loadDocumentList();
            if (typeof showToast === 'function') showToast("Document deleted successfully");
        }
    } catch (e) { if (typeof showToast === 'function') showToast("Error deleting.", "error"); }
}

async function handleSettingsUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    if (typeof showToast === 'function') showToast("Uploading " + file.name + "...");
    
    try {
        const res = await fetch("/admin/upload-pdf", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token },
            body: formData
        });
        if (res.ok) {
            if (typeof showToast === 'function') showToast("Document indexed!");
            loadDocumentList();
        } else {
            const err = await res.json();
            if (typeof showToast === 'function') showToast(err.detail || "Upload failed", "error");
        }
    } catch(e) { if (typeof showToast === 'function') showToast("Network error during upload.", "error"); }
}

// 4. MODEL DELETE (Used in Models Tab)
async function deleteModel(modelName) {
    if (typeof showConfirm !== 'function') return;
    const confirmed = await showConfirm("Delete Model?", `Are you sure you want to delete ${modelName}? This will free up disk space.`, "Delete");
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/models/${modelName}`, { 
            method: "DELETE", 
            headers: { "Authorization": "Bearer " + token }
        });
        if (res.ok) {
            if (typeof showToast === 'function') showToast(`${modelName} deleted.`);
            loadModels();
        } else {
            const data = await res.json();
            if (typeof showToast === 'function') showToast(data.detail || "Delete failed", "error");
        }
    } catch(e) { console.error("Error deleting model:", e); }
}
