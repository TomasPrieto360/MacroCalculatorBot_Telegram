// MacroBot Mobile App Logic
let currentUser = 'default';
let currentUserData = null;
let selectedFoodForLog = null;
let currentAiParsedFood = null;

// Inicialización de Telegram WebApp
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

document.addEventListener('DOMContentLoaded', () => {
    initApp();
    registerServiceWorker();
});

async function initApp() {
    setupEventListeners();
    await loadUsers();
    
    // Auto-detectar usuario de Telegram si está disponible
    if (tg?.initDataUnsafe?.user?.id) {
        const tgId = str(tg.initDataUnsafe.user.id);
        const userSelect = document.getElementById('userSelect');
        // Agregar si no existe
        if (![...userSelect.options].some(opt => opt.value === tgId)) {
            const newOpt = document.createElement('option');
            newOpt.value = tgId;
            newOpt.textContent = `Telegram: ${tg.initDataUnsafe.user.first_name || tgId}`;
            userSelect.prepend(newOpt);
        }
        userSelect.value = tgId;
        currentUser = tgId;
    }

    await loadUserData();
}

// Cargar lista de usuarios desde la API
async function loadUsers() {
    try {
        const res = await fetch('/api/users');
        const users = await res.json();
        const userSelect = document.getElementById('userSelect');
        userSelect.innerHTML = '';

        if (users.length === 0) {
            userSelect.innerHTML = '<option value="invitado">Invitado</option>';
        } else {
            users.forEach(u => {
                const opt = document.createElement('option');
                opt.value = u.id;
                opt.textContent = u.name || `Usuario ${u.id}`;
                userSelect.appendChild(opt);
            });
        }

        currentUser = userSelect.value;
    } catch (e) {
        console.error('Error cargando usuarios:', e);
    }
}

// Cargar datos completos del usuario activo
async function loadUserData() {
    if (!currentUser) return;
    try {
        const res = await fetch(`/api/user/${currentUser}`);
        currentUserData = await res.json();
        renderDashboard();
        renderHistory();
        renderProfile();
    } catch (e) {
        console.error('Error cargando datos de usuario:', e);
    }
}

// Renderizar Anillo y Barras de Macros
function renderDashboard() {
    if (!currentUserData) return;

    const kcalConsumed = currentUserData.kcal || 0;
    const kcalGoal = currentUserData.meta_kcal || 2000;
    const kcalRemaining = Math.max(0, kcalGoal - kcalConsumed);

    document.getElementById('kcalConsumed').textContent = Math.round(kcalConsumed);
    document.getElementById('kcalGoal').textContent = Math.round(kcalGoal);
    document.getElementById('kcalRemaining').textContent = Math.round(kcalRemaining);

    // Actualizar progreso del Anillo SVG (Radio = 70, Perímetro = 440)
    const ringFill = document.getElementById('calorieProgress');
    const percent = Math.min(100, (kcalConsumed / kcalGoal) * 100);
    const offset = 440 - (440 * percent) / 100;
    ringFill.style.strokeDashoffset = offset;

    // Macros
    const protCurrent = currentUserData.proteinas || 0;
    const protGoal = currentUserData.meta_proteinas || 160;
    document.getElementById('protCurrent').textContent = protCurrent.toFixed(1);
    document.getElementById('protGoal').textContent = protGoal;
    document.getElementById('protBar').style.width = `${Math.min(100, (protCurrent / protGoal) * 100)}%`;

    const carbCurrent = currentUserData.carbos || 0;
    document.getElementById('carbCurrent').textContent = carbCurrent.toFixed(1);
    document.getElementById('carbBar').style.width = `${Math.min(100, (carbCurrent / 250) * 100)}%`;

    const fatCurrent = currentUserData.grasas || 0;
    document.getElementById('fatCurrent').textContent = fatCurrent.toFixed(1);
    document.getElementById('fatBar').style.width = `${Math.min(100, (fatCurrent / 70) * 100)}%`;
}

// Renderizar Historial
function renderHistory() {
    const list = document.getElementById('historyList');
    const countBadge = document.getElementById('historyCount');
    const history = currentUserData?.historial_hoy || [];

    countBadge.textContent = `${history.length} comidas`;

    if (history.length === 0) {
        list.innerHTML = '<div class="placeholder-msg">Aún no registraste alimentos hoy.</div>';
        return;
    }

    list.innerHTML = history.map(item => `
        <div class="history-item">
            <div class="history-item-left">
                <h4>${item.alimento}</h4>
                <p>${item.cantidad_str} • P: ${item.proteinas.toFixed(1)}g | C: ${item.carbos.toFixed(1)}g | G: ${item.grasas.toFixed(1)}g</p>
            </div>
            <div class="history-item-right">
                <span class="history-kcal">${Math.round(item.kcal)} kcal</span>
                <button class="delete-item-btn" onclick="deleteHistoryItem('${item.id}')" title="Eliminar">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Renderizar formulario de Perfil
function renderProfile() {
    if (!currentUserData) return;
    document.getElementById('profGoalKcal').value = currentUserData.meta_kcal || 2000;
    document.getElementById('profGoalProt').value = currentUserData.meta_proteinas || 160;
}

// Event Listeners generales
function setupEventListeners() {
    // Selector de Usuario
    document.getElementById('userSelect').addEventListener('change', (e) => {
        currentUser = e.target.value;
        loadUserData();
    });

    // Refresh
    document.getElementById('btnRefresh').addEventListener('click', loadUserData);

    // Búsqueda con Debounce
    let searchTimeout;
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.getElementById('btnClearSearch');

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        clearBtn.classList.toggle('hidden', query.length === 0);
        
        clearTimeout(searchTimeout);
        if (query.length < 2) {
            document.getElementById('searchResults').innerHTML = '<div class="placeholder-msg">Buscá un alimento de tu base de datos o escanealo.</div>';
            return;
        }

        searchTimeout = setTimeout(() => performSearch(query), 300);
    });

    clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        clearBtn.classList.add('hidden');
        document.getElementById('searchResults').innerHTML = '<div class="placeholder-msg">Buscá un alimento de tu base de datos o escanealo.</div>';
    });

    // Modal de registro
    document.getElementById('btnCancelLog').addEventListener('click', closeLogModal);
    document.getElementById('btnConfirmLog').addEventListener('click', confirmLogFood);

    // Formularios IA
    document.getElementById('btnSubmitAiText').addEventListener('click', submitAiText);
    document.getElementById('aiPhotoInput').addEventListener('change', handleImageSelect);
    document.getElementById('btnSubmitAiPhoto').addEventListener('click', submitAiPhoto);
    document.getElementById('btnLogAiResult').addEventListener('click', logAiResult);

    // Guardar Perfil
    document.getElementById('profileForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const meta_kcal = parseFloat(document.getElementById('profGoalKcal').value);
        const meta_proteinas = parseFloat(document.getElementById('profGoalProt').value);

        await fetch(`/api/user/${currentUser}/profile`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ meta_kcal, meta_proteinas })
        });

        alert('¡Configuración guardada!');
        await loadUserData();
    });
}

// Búsqueda en API
async function performSearch(query) {
    const resultsContainer = document.getElementById('searchResults');
    resultsContainer.innerHTML = '<div class="placeholder-msg"><i class="fa-solid fa-spinner fa-spin"></i> Buscando...</div>';

    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const items = await res.json();

        if (items.length === 0) {
            resultsContainer.innerHTML = '<div class="placeholder-msg">No se encontraron alimentos.</div>';
            return;
        }

        resultsContainer.innerHTML = items.map(item => `
            <div class="food-item-card" onclick='openLogModal(${JSON.stringify(item).replace(/'/g, "&apos;")})'>
                <div class="food-item-info">
                    <h4>${item.alimento}</h4>
                    <p>100g: ${Math.round(item.kcal)} kcal | P: ${item.proteinas}g | C: ${item.carbos}g | G: ${item.grasas}g</p>
                </div>
                <i class="fa-solid fa-plus text-orange"></i>
            </div>
        `).join('');
    } catch (e) {
        resultsContainer.innerHTML = '<div class="placeholder-msg">Error al realizar la búsqueda.</div>';
    }
}

// Modal Log Food
function openLogModal(food) {
    selectedFoodForLog = food;
    document.getElementById('modalFoodTitle').textContent = food.alimento;
    document.getElementById('modalFoodMacros').textContent = 
        `100g: ${Math.round(food.kcal)} kcal | P: ${food.proteinas}g | C: ${food.carbos}g | G: ${food.grasas}g`;
    document.getElementById('logQuantity').value = 100;
    document.getElementById('logModal').classList.remove('hidden');
}

function closeLogModal() {
    document.getElementById('logModal').classList.add('hidden');
    selectedFoodForLog = null;
}

async function confirmLogFood() {
    if (!selectedFoodForLog) return;
    const qty = parseFloat(document.getElementById('logQuantity').value) || 100;
    const unit = document.getElementById('logUnit').value;

    try {
        await fetch(`/api/user/${currentUser}/log`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                alimento: selectedFoodForLog.alimento,
                cantidad: qty,
                unidad: unit,
                stats: selectedFoodForLog
            })
        });

        closeLogModal();
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        await loadUserData();
        switchTab('tab-dashboard');
    } catch (e) {
        alert('Error registrando alimento');
    }
}

// Eliminar Registro Historial
async function deleteHistoryItem(itemId) {
    if (!confirm('¿Eliminar esta comida del registro?')) return;
    try {
        await fetch(`/api/user/${currentUser}/history/${itemId}`, { method: 'DELETE' });
        await loadUserData();
    } catch (e) {
        alert('Error al eliminar');
    }
}

// IA - Texto
async function submitAiText() {
    const text = document.getElementById('aiTextInput').value.trim();
    if (!text) return alert('Escribí algo para analizar.');

    const btn = document.getElementById('btnSubmitAiText');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analizando...';

    try {
        const res = await fetch('/api/ai/parse-food', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ text })
        });
        const data = await res.json();
        
        if (data.status === 'ok') {
            displayAiResult(data.parsed);
        } else {
            alert(data.message || 'No se pudo interpretar');
        }
    } catch (e) {
        alert('Error consultando la IA');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-sparkles"></i> Analizar con IA';
    }
}

// IA - Foto
function handleImageSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
        document.getElementById('imagePreview').src = evt.target.result;
        document.getElementById('imagePreviewContainer').classList.remove('hidden');
        document.getElementById('uploadText').textContent = file.name;
        document.getElementById('btnSubmitAiPhoto').disabled = false;
    };
    reader.readAsDataURL(file);
}

async function submitAiPhoto() {
    const imgSrc = document.getElementById('imagePreview').src;
    if (!imgSrc) return;

    const btn = document.getElementById('btnSubmitAiPhoto');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Procesando Foto...';

    try {
        const base64Data = imgSrc.split(',')[1];
        const res = await fetch('/api/ai/scan-label', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ image_base64: base64Data })
        });
        const data = await res.json();

        if (data.status === 'ok') {
            displayAiResult(data.parsed);
        } else {
            alert(data.message || 'No se pudo escanear la etiqueta');
        }
    } catch (e) {
        alert('Error en escáner de foto');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Escanear Etiqueta';
    }
}

function displayAiResult(parsed) {
    currentAiParsedFood = parsed;
    const box = document.getElementById('aiResultBox');
    const content = document.getElementById('aiResultContent');

    content.innerHTML = `
        <strong>${parsed.alimento || 'Alimento'}</strong><br>
        🔥 Calorías: ${Math.round(parsed.kcal || 0)} kcal<br>
        🥩 Proteínas: ${(parsed.proteinas || 0).toFixed(1)}g | 🍞 Carbos: ${(parsed.carbos || 0).toFixed(1)}g | 🥑 Grasas: ${(parsed.grasas || 0).toFixed(1)}g
    `;

    box.classList.remove('hidden');
}

async function logAiResult() {
    if (!currentAiParsedFood) return;
    try {
        await fetch(`/api/user/${currentUser}/log`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                alimento: currentAiParsedFood.alimento || 'Comida IA',
                cantidad: 100,
                unidad: 'g',
                stats: currentAiParsedFood
            })
        });

        document.getElementById('aiResultBox').classList.add('hidden');
        currentAiParsedFood = null;
        await loadUserData();
        switchTab('tab-dashboard');
    } catch (e) {
        alert('Error guardando resultado IA');
    }
}

// Navegación por pestañas
function switchTab(tabId) {
    document.querySelectorAll('.tab-page').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    document.getElementById(tabId).classList.add('active');
    const navIndex = ['tab-dashboard', 'tab-search', 'tab-ai', 'tab-diary', 'tab-profile'].indexOf(tabId);
    if (navIndex !== -1) {
        document.querySelectorAll('.bottom-nav .nav-item')[navIndex].classList.add('active');
    }
}

function switchAiMode(mode) {
    document.getElementById('btnAiTextTab').classList.toggle('active', mode === 'text');
    document.getElementById('btnAiPhotoTab').classList.toggle('active', mode === 'photo');
    document.getElementById('aiModeText').classList.toggle('hidden', mode !== 'text');
    document.getElementById('aiModePhoto').classList.toggle('hidden', mode !== 'photo');
}

// Registrar Service Worker PWA
function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(err => console.log('SW Error:', err));
    }
}
