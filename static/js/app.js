// MacroBot Mobile PWA App Logic - Standalone
let currentUser = 'default';
let currentUserData = null;
let selectedFoodForLog = null;
let currentAiParsedFood = null;
let currentAiMode = 'meal'; // 'meal', 'label', 'text'

// Variables para Escáner de Código de Barras y Porciones
let html5QrcodeScanner = null;
let isCameraRunning = false;
let currentFacingMode = 'environment';
let currentLabelSubMode = 'live'; // 'live', 'photo'
let selectedDetectedFood = null;

// Inicialización de Telegram WebApp SDK (opcional si corre dentro de Telegram)
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
        const tgId = String(tg.initDataUnsafe.user.id);
        const userSelect = document.getElementById('userSelect');
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

// Cargar usuarios
async function loadUsers() {
    try {
        const res = await fetch('/api/users');
        const users = await res.json();
        const userSelect = document.getElementById('userSelect');
        userSelect.innerHTML = '';

        if (users.length === 0) {
            userSelect.innerHTML = '<option value="defecto">Usuario Principal</option>';
        } else {
            users.forEach(u => {
                const opt = document.createElement('option');
                opt.value = u.id;
                opt.textContent = u.name || `Usuario ${u.id}`;
                userSelect.appendChild(opt);
            });
        }
        currentUser = userSelect.value || 'defecto';
    } catch (e) {
        console.error('Error cargando usuarios:', e);
        const userSelect = document.getElementById('userSelect');
        userSelect.innerHTML = '<option value="defecto">Usuario Principal</option>';
        currentUser = 'defecto';
    }
}

// Cargar datos de usuario activo
async function loadUserData() {
    if (!currentUser) return;
    try {
        const res = await fetch(`/api/user/${currentUser}`);
        currentUserData = await res.json();
        renderDashboard();
        renderHistory();
        renderFavorites();
        renderProfile();
        renderPastDaysHistory();
    } catch (e) {
        console.error('Error cargando datos de usuario:', e);
    }
}

// Renderizar Dashboard Principal
function renderDashboard() {
    if (!currentUserData) return;

    // Racha
    document.getElementById('streakCount').textContent = currentUserData.racha_dias || 0;

    // Calorías
    const kcalConsumed = currentUserData.kcal || 0;
    const kcalGoal = currentUserData.meta_kcal || 2000;
    const kcalRemaining = Math.max(0, kcalGoal - kcalConsumed);

    document.getElementById('kcalConsumed').textContent = Math.round(kcalConsumed);
    document.getElementById('kcalGoal').textContent = Math.round(kcalGoal);
    document.getElementById('kcalRemaining').textContent = Math.round(kcalRemaining);

    // Anillo SVG (Radio 70 -> Perímetro 440)
    const ringFill = document.getElementById('calorieProgress');
    const percent = Math.min(100, (kcalConsumed / kcalGoal) * 100);
    const offset = 440 - (440 * percent) / 100;
    ringFill.style.strokeDashoffset = offset;

    // Macros (Proteínas, Carbos, Grasas)
    const protCurrent = currentUserData.proteinas || 0;
    const protGoal = currentUserData.meta_proteinas || 160;
    document.getElementById('protCurrent').textContent = protCurrent.toFixed(1);
    document.getElementById('protGoal').textContent = protGoal;
    document.getElementById('protBar').style.width = `${Math.min(100, (protCurrent / protGoal) * 100)}%`;

    const carbCurrent = currentUserData.carbos || 0;
    const carbGoal = currentUserData.meta_carbos || 250;
    document.getElementById('carbCurrent').textContent = carbCurrent.toFixed(1);
    document.getElementById('carbGoal').textContent = carbGoal;
    document.getElementById('carbBar').style.width = `${Math.min(100, (carbCurrent / carbGoal) * 100)}%`;

    const fatCurrent = currentUserData.grasas || 0;
    const fatGoal = currentUserData.meta_grasas || 65;
    document.getElementById('fatCurrent').textContent = fatCurrent.toFixed(1);
    document.getElementById('fatGoal').textContent = fatGoal;
    document.getElementById('fatBar').style.width = `${Math.min(100, (fatCurrent / fatGoal) * 100)}%`;
}

// Renderizar Historial de Hoy
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
                <h4 style="text-transform: capitalize;">${item.alimento}</h4>
                <p>${item.cantidad_str} • P: ${(item.proteinas||0).toFixed(1)}g | C: ${(item.carbos||0).toFixed(1)}g | G: ${(item.grasas||0).toFixed(1)}g</p>
            </div>
            <div class="history-item-right" style="display:flex; align-items:center; gap:10px;">
                <span class="history-kcal" style="font-weight:700; color:var(--color-orange);">${Math.round(item.kcal)} kcal</span>
                <button class="delete-item-btn" onclick="deleteHistoryItem('${item.id}')" title="Eliminar">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Renderizar Favoritos
function renderFavorites() {
    const list = document.getElementById('favoritesList');
    const badge = document.getElementById('favCountBadge');
    const favs = currentUserData?.favoritos || {};
    const keys = Object.keys(favs);

    badge.textContent = `${keys.length} ítems`;

    if (keys.length === 0) {
        list.innerHTML = '<div class="placeholder-msg">No tenés alimentos en favoritos aún. Guardá los que usés frecuentemente.</div>';
        return;
    }

    list.innerHTML = keys.map(k => {
        const item = favs[k];
        return `
            <div class="fav-item-card">
                <div class="food-item-info" onclick='logFavoriteItem(${JSON.stringify(item).replace(/'/g, "&apos;")})'>
                    <h4 style="text-transform: capitalize;"><i class="fa-solid fa-star text-gold"></i> ${item.nombre}</h4>
                    <p>${Math.round(item.kcal)} kcal | P: ${item.proteinas}g | C: ${item.carbos}g | G: ${item.grasas}g</p>
                </div>
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-primary" style="padding:6px 12px; font-size:0.8rem;" onclick='logFavoriteItem(${JSON.stringify(item).replace(/'/g, "&apos;")})'>
                        <i class="fa-solid fa-plus"></i> Usar
                    </button>
                    <button class="delete-item-btn" onclick="deleteFavoriteItem('${item.nombre}')" title="Eliminar de favoritos">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Renderizar Perfil & TDEE
function renderProfile() {
    if (!currentUserData) return;
    const perfil = currentUserData.perfil_fisico || {};
    if (perfil.peso) document.getElementById('tdeePeso').value = perfil.peso;
    if (perfil.altura) document.getElementById('tdeeAltura').value = perfil.altura;
    if (perfil.edad) document.getElementById('tdeeEdad').value = perfil.edad;
    if (perfil.sexo) document.getElementById('tdeeSexo').value = perfil.sexo;
    if (perfil.actividad) document.getElementById('tdeeActividad').value = perfil.actividad;
    if (perfil.objetivo) document.getElementById('tdeeObjetivo').value = perfil.objetivo;
}

// Renderizar Historial de Días Anteriores
function renderPastDaysHistory() {
    const list = document.getElementById('pastDaysHistoryList');
    const pastDays = currentUserData?.historial_dias || [];

    if (pastDays.length === 0) {
        list.innerHTML = '<div class="placeholder-msg">Cuando cierres un día con "Terminar Día", aparecerá guardado aquí.</div>';
        return;
    }

    list.innerHTML = pastDays.map(day => `
        <div class="fav-item-card">
            <div class="food-item-info">
                <h4><i class="fa-solid fa-calendar-check text-blue"></i> ${day.fecha}</h4>
                <p>Consumo: <strong>${Math.round(day.kcal)}</strong> / ${Math.round(day.meta_kcal)} kcal • ${day.comidas_count} comidas</p>
                <p style="font-size:0.75rem; color:var(--text-secondary);">P: ${day.proteinas}g | C: ${day.carbos}g | G: ${day.grasas}g</p>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <span class="badge ${day.cumplido ? 'badge-success' : ''}">${day.cumplido ? '✅ Meta Cumplida' : '📊 Cerrado'}</span>
                <button class="delete-item-btn" onclick="deleteHistoryDay('${day.fecha}')" title="Eliminar registro de esta fecha">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        </div>
    `).join('');
}

async function deleteHistoryDay(fecha) {
    if (!confirm(`¿Eliminar el registro histórico del día ${fecha}?`)) return;
    try {
        const res = await fetch(`/api/user/${currentUser}/history-day/${fecha}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            await loadUserData();
        } else {
            alert('Error al eliminar fecha del historial');
        }
    } catch (e) {
        alert('Error de red al eliminar fecha');
    }
}

// Setup Event Listeners
function setupEventListeners() {
    // Selector Usuario
    document.getElementById('userSelect').addEventListener('change', (e) => {
        currentUser = e.target.value;
        loadUserData();
    });

    // Refresh
    document.getElementById('btnRefresh').addEventListener('click', loadUserData);

    // Búsqueda
    let searchTimeout;
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.getElementById('btnClearSearch');

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        clearBtn.classList.toggle('hidden', query.length === 0);
        clearTimeout(searchTimeout);
        if (query.length < 2) {
            document.getElementById('searchResults').innerHTML = '<div class="placeholder-msg">Escribí el nombre de un alimento para buscar.</div>';
            return;
        }
        searchTimeout = setTimeout(() => performSearch(query), 300);
    });

    clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        clearBtn.classList.add('hidden');
        document.getElementById('searchResults').innerHTML = '<div class="placeholder-msg">Escribí el nombre de un alimento para buscar.</div>';
    });

    // Modales
    document.getElementById('btnCancelLog').addEventListener('click', closeLogModal);
    document.getElementById('btnConfirmLog').addEventListener('click', confirmLogFood);
    document.getElementById('logQuantity').addEventListener('input', updateLivePreview);
    document.getElementById('logUnit').addEventListener('change', updateLivePreview);

    // Botón Cerrar Día y Atajos de Fecha
    document.getElementById('btnOpenCloseDay').addEventListener('click', openCloseDayModal);
    document.getElementById('btnCancelCloseDay').addEventListener('click', closeCloseDayModal);
    document.getElementById('btnConfirmCloseDay').addEventListener('click', confirmCloseDay);
    
    document.getElementById('btnDateYesterday').addEventListener('click', () => {
        const d = new Date();
        d.setDate(d.getDate() - 1);
        document.getElementById('closeDayDate').value = d.toISOString().split('T')[0];
    });

    document.getElementById('btnDateToday').addEventListener('click', () => {
        document.getElementById('closeDayDate').value = new Date().toISOString().split('T')[0];
    });

    // IA / Foto & Cámara
    document.getElementById('aiPhotoInput').addEventListener('change', handleImageSelect);
    document.getElementById('btnRemoveImage').addEventListener('click', resetPhotoUpload);
    document.getElementById('btnSubmitAiPhoto').addEventListener('click', submitAiPhoto);
    document.getElementById('btnSubmitAiText').addEventListener('click', submitAiText);
    document.getElementById('btnLogAiResult').addEventListener('click', logAiResult);
    document.getElementById('btnSaveFavoriteAi').addEventListener('click', saveFavoriteFromAi);

    // Escáner en Vivo & Controles de Cámara
    document.getElementById('btnToggleCamera').addEventListener('click', toggleLiveCamera);
    document.getElementById('btnSwitchCamera').addEventListener('click', switchCameraFacing);

    // Modal Porción / Gramos Detectados
    document.getElementById('portionGramsInput').addEventListener('input', updatePortionPreview);
    document.getElementById('btnConfirmPortionLog').addEventListener('click', confirmPortionLog);
    document.getElementById('btnSavePortionFav').addEventListener('click', savePortionFavorite);
    document.getElementById('btnCancelPortion').addEventListener('click', closePortionModal);

    // Recetas Heladera
    document.getElementById('btnGenerateFridgeRecipes').addEventListener('click', generateFridgeRecipes);

    // Formulario TDEE
    document.getElementById('tdeeForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const peso = parseFloat(document.getElementById('tdeePeso').value);
        const altura = parseFloat(document.getElementById('tdeeAltura').value);
        const edad = parseFloat(document.getElementById('tdeeEdad').value);
        const sexo = document.getElementById('tdeeSexo').value;
        const actividad = document.getElementById('tdeeActividad').value;
        const objetivo = document.getElementById('tdeeObjetivo').value;

        try {
            const res = await fetch(`/api/user/${currentUser}/calculate-tdee`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ peso, altura, edad, sexo, actividad, objetivo })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                alert(`¡Metas recalculadas!\nMeta Calorías: ${data.meta_kcal} kcal\nProteínas: ${data.meta_proteinas}g`);
                await loadUserData();
            }
        } catch (e) {
            alert('Error calculando TDEE');
        }
    });
}

// Búsqueda en API
async function performSearch(query) {
    const resultsContainer = document.getElementById('searchResults');
    resultsContainer.innerHTML = '<div class="placeholder-msg"><i class="fa-solid fa-spinner fa-spin"></i> Buscando alimentos...</div>';

    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const items = await res.json();

        if (items.length === 0) {
            resultsContainer.innerHTML = '<div class="placeholder-msg">No se encontraron alimentos en la base de datos.</div>';
            return;
        }

        resultsContainer.innerHTML = items.map(item => `
            <div class="food-item-card" onclick='openLogModal(${JSON.stringify(item).replace(/'/g, "&apos;")})'>
                <div class="food-item-info">
                    <h4 style="text-transform: capitalize;">${item.alimento}</h4>
                    <p>100g: ${Math.round(item.kcal)} kcal | P: ${item.proteinas}g | C: ${item.carbos}g | G: ${item.grasas}g</p>
                </div>
                <i class="fa-solid fa-circle-plus text-orange" style="font-size:1.3rem;"></i>
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
    updateLivePreview();
    document.getElementById('logModal').classList.remove('hidden');
}

function updateLivePreview() {
    if (!selectedFoodForLog) return;
    const qty = parseFloat(document.getElementById('logQuantity').value) || 100;
    const unit = document.getElementById('logUnit').value;

    let grams = qty;
    if (unit === 'u' && selectedFoodForLog.peso_unidad) {
        grams = qty * selectedFoodForLog.peso_unidad;
    }

    const kcal = ((selectedFoodForLog.kcal || 0) * grams) / 100;
    const prot = ((selectedFoodForLog.proteinas || 0) * grams) / 100;
    const carb = ((selectedFoodForLog.carbos || 0) * grams) / 100;
    const fat = ((selectedFoodForLog.grasas || 0) * grams) / 100;

    document.getElementById('modalLivePreview').innerHTML = `
        ⚡ Total a registrar: <strong>${Math.round(kcal)} kcal</strong><br>
        🥩 Proteínas: <strong>${prot.toFixed(1)}g</strong> | 🌾 Carbos: <strong>${carb.toFixed(1)}g</strong> | 🥑 Grasas: <strong>${fat.toFixed(1)}g</strong>
    `;
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

// Modal Cerrar Día
function openCloseDayModal() {
    if (!currentUserData) return;
    const consumedKcal = Math.round(currentUserData.kcal || 0);
    const goalKcal = Math.round(currentUserData.meta_kcal || 2000);
    const comidasCount = (currentUserData.historial_hoy || []).length;

    // Inicializar fecha en HOY
    const todayStr = new Date().toISOString().split('T')[0];
    document.getElementById('closeDayDate').value = todayStr;

    document.getElementById('closeDaySummary').innerHTML = `
        <div style="font-size:1.1rem; font-weight:700; margin-bottom:6px;">Total consumido hoy: <span class="text-orange">${consumedKcal} kcal</span> / ${goalKcal} kcal</div>
        <div style="font-size:0.88rem; color:var(--text-secondary);">Proteínas: ${(currentUserData.proteinas||0).toFixed(1)}g | Carbos: ${(currentUserData.carbos||0).toFixed(1)}g | Grasas: ${(currentUserData.grasas||0).toFixed(1)}g</div>
        <div style="font-size:0.85rem; margin-top:6px; color:var(--text-muted);">${comidasCount} comidas registradas en la jornada.</div>
    `;
    document.getElementById('closeDayModal').classList.remove('hidden');
}

function closeCloseDayModal() {
    document.getElementById('closeDayModal').classList.add('hidden');
}

async function confirmCloseDay() {
    const selectedDate = document.getElementById('closeDayDate').value;
    if (!selectedDate) return alert('Por favor seleccioná una fecha válida.');

    try {
        const res = await fetch(`/api/user/${currentUser}/close-day`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ fecha: selectedDate })
        });
        const data = await res.json();
        closeCloseDayModal();
        if (data.status === 'ok') {
            alert(`🎉 ¡Día Cerrado (${selectedDate})!\nTu racha actual es de ${data.racha_dias} día(s).`);
            await loadUserData();
            switchTab('tab-dashboard');
        } else {
            alert(`Error: ${data.message || 'No se pudo cerrar el día'}`);
        }
    } catch (e) {
        alert('Error cerrando el día');
    }
}

// IA - Selección de Modo Principal (Plato, Etiqueta, Texto)
function switchAiMode(mode) {
    currentAiMode = mode;
    document.getElementById('btnAiMealTab').classList.toggle('active', mode === 'meal');
    document.getElementById('btnAiLabelTab').classList.toggle('active', mode === 'label');
    document.getElementById('btnAiTextTab').classList.toggle('active', mode === 'text');

    const labelSubTabs = document.getElementById('labelSubTabs');
    const photoContainer = document.getElementById('aiModePhoto');
    const liveScannerContainer = document.getElementById('aiModeLiveScanner');
    const textContainer = document.getElementById('aiModeText');
    const photoDetailsGroup = document.getElementById('aiPhotoDetailsGroup');

    if (mode === 'meal') {
        stopLiveScanner();
        labelSubTabs.classList.add('hidden');
        liveScannerContainer.classList.add('hidden');
        photoContainer.classList.remove('hidden');
        textContainer.classList.add('hidden');
        photoDetailsGroup.classList.remove('hidden');
        document.getElementById('aiTabSubtitle').innerHTML = 'Subí una foto de tu <strong>Plato de Comida</strong> y la IA identificará la preparación y porción.';
    } else if (mode === 'label') {
        labelSubTabs.classList.remove('hidden');
        photoDetailsGroup.classList.add('hidden'); // Ocultar detalles manuales en modo etiqueta
        textContainer.classList.add('hidden');
        document.getElementById('aiTabSubtitle').innerHTML = 'Escaneá el <strong>Código de Barras</strong> en vivo con la cámara o subí una foto de la <strong>Etiqueta Nutricional</strong>.';
        switchLabelSubMode(currentLabelSubMode || 'live');
    } else if (mode === 'text') {
        stopLiveScanner();
        labelSubTabs.classList.add('hidden');
        liveScannerContainer.classList.add('hidden');
        photoContainer.classList.add('hidden');
        textContainer.classList.remove('hidden');
        document.getElementById('aiTabSubtitle').innerHTML = 'Describí lo que comiste en texto libre y la IA calculará tus calorías y macros.';
    }
}

// IA - Selección de Sub-Modo de Etiquetas (Cámara en Vivo vs Subir Foto)
function switchLabelSubMode(subMode) {
    currentLabelSubMode = subMode;
    document.getElementById('btnSubTabLive').classList.toggle('active', subMode === 'live');
    document.getElementById('btnSubTabPhoto').classList.toggle('active', subMode === 'photo');

    const liveScannerContainer = document.getElementById('aiModeLiveScanner');
    const photoContainer = document.getElementById('aiModePhoto');

    if (subMode === 'live') {
        photoContainer.classList.add('hidden');
        liveScannerContainer.classList.remove('hidden');
        startLiveScanner();
    } else {
        stopLiveScanner();
        liveScannerContainer.classList.add('hidden');
        photoContainer.classList.remove('hidden');
    }
}

// --- CONTROL DE CÁMARA EN VIVO & ESCÁNER DE CÓDIGOS ---
async function toggleLiveCamera() {
    if (isCameraRunning) {
        await stopLiveScanner();
    } else {
        await startLiveScanner();
    }
}

async function switchCameraFacing() {
    currentFacingMode = (currentFacingMode === 'environment') ? 'user' : 'environment';
    if (isCameraRunning) {
        await stopLiveScanner();
        await startLiveScanner();
    }
}

async function startLiveScanner() {
    if (typeof Html5Qrcode === 'undefined') {
        alert('Cargando motor de cámara... Intentá de nuevo en un segundo.');
        return;
    }

    const btnToggle = document.getElementById('btnToggleCamera');
    btnToggle.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...';

    try {
        if (!html5QrcodeScanner) {
            html5QrcodeScanner = new Html5Qrcode("liveBarcodeReader");
        }

        const config = {
            fps: 15,
            qrbox: { width: 220, height: 170 },
            aspectRatio: 1.333333
        };

        await html5QrcodeScanner.start(
            { facingMode: currentFacingMode },
            config,
            onBarcodeScanned,
            () => {}
        );

        isCameraRunning = true;
        btnToggle.classList.remove('btn-primary');
        btnToggle.classList.add('btn-secondary');
        btnToggle.innerHTML = '<i class="fa-solid fa-video-slash"></i> Detener Cámara';
    } catch (e) {
        console.error('Error al iniciar cámara:', e);
        btnToggle.classList.remove('btn-secondary');
        btnToggle.classList.add('btn-primary');
        btnToggle.innerHTML = '<i class="fa-solid fa-video"></i> Iniciar Cámara';
        isCameraRunning = false;
    }
}

async function stopLiveScanner() {
    if (html5QrcodeScanner && isCameraRunning) {
        try {
            await html5QrcodeScanner.stop();
        } catch (e) {
            console.error('Error al detener cámara:', e);
        }
    }
    isCameraRunning = false;
    const btnToggle = document.getElementById('btnToggleCamera');
    if (btnToggle) {
        btnToggle.classList.remove('btn-secondary');
        btnToggle.classList.add('btn-primary');
        btnToggle.innerHTML = '<i class="fa-solid fa-video"></i> Iniciar Cámara';
    }
}

let lastScannedCode = null;
let lastScanTime = 0;

async function onBarcodeScanned(decodedText) {
    const now = Date.now();
    if (decodedText === lastScannedCode && (now - lastScanTime) < 3000) {
        return;
    }
    lastScannedCode = decodedText;
    lastScanTime = now;

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
    } else if (navigator.vibrate) {
        navigator.vibrate([100, 50, 100]);
    }

    await stopLiveScanner();
    fetchBarcodeProduct(decodedText);
}

async function fetchBarcodeProduct(barcode) {
    try {
        const res = await fetch(`/api/barcode/${encodeURIComponent(barcode)}`);
        const data = await res.json();

        if (data.status === 'ok' && data.alimento) {
            openPortionModal(data.alimento);
        } else {
            alert(`🔍 Código (${barcode}) no encontrado en Open Food Facts.\n\nPasá a la pestaña "Foto de Etiqueta" para sacarle foto a la información nutricional con la IA.`);
            switchLabelSubMode('photo');
        }
    } catch (e) {
        alert(`Error al consultar el código de barras ${barcode}`);
    }
}

// --- MODAL DE SELECCIÓN DE PORCIÓN / GRAMOS CONSUMIDOS ---
function openPortionModal(food) {
    selectedDetectedFood = food;
    const modal = document.getElementById('portionModal');
    const title = document.getElementById('portionFoodTitle');
    const subtitle = document.getElementById('portionFoodSubtitle');
    const btnFullPkg = document.getElementById('btnFullPackage');

    title.textContent = food.alimento || food.nombre || 'Producto Detectado';

    const kcal100 = food.kcal || 0;
    const p100 = food.proteinas || 0;
    const c100 = food.carbos || 0;
    const g100 = food.grasas || 0;

    subtitle.textContent = `Valores 100g: ${Math.round(kcal100)} kcal | P: ${p100.toFixed(1)}g | C: ${c100.toFixed(1)}g | G: ${g100.toFixed(1)}g`;

    const pkgWeight = food.peso_porcion || food.peso_unidad || food.cantidad_estimada_g;
    if (pkgWeight && pkgWeight > 0) {
        btnFullPkg.textContent = `📦 Envase/Porción (${pkgWeight}g)`;
        btnFullPkg.dataset.grams = pkgWeight;
        btnFullPkg.classList.remove('hidden');
    } else {
        btnFullPkg.classList.add('hidden');
    }

    const defaultGrams = pkgWeight || 100;
    document.getElementById('portionGramsInput').value = defaultGrams;

    document.querySelectorAll('.btn-portion-chip').forEach(chip => {
        chip.classList.toggle('active', chip.textContent.trim() === `${defaultGrams}g`);
    });

    updatePortionPreview();
    modal.classList.remove('hidden');
}

function setPortionGrams(grams) {
    document.getElementById('portionGramsInput').value = grams;
    document.querySelectorAll('.btn-portion-chip').forEach(chip => {
        chip.classList.toggle('active', chip.textContent.trim() === `${grams}g`);
    });
    updatePortionPreview();
}

function setFullPackagePortion() {
    const btnFullPkg = document.getElementById('btnFullPackage');
    const grams = parseFloat(btnFullPkg.dataset.grams) || 100;
    document.getElementById('portionGramsInput').value = grams;
    document.querySelectorAll('.btn-portion-chip').forEach(chip => chip.classList.remove('active'));
    btnFullPkg.classList.add('active');
    updatePortionPreview();
}

function updatePortionPreview() {
    if (!selectedDetectedFood) return;

    const grams = parseFloat(document.getElementById('portionGramsInput').value) || 100;
    const kcal100 = selectedDetectedFood.kcal || 0;
    const p100 = selectedDetectedFood.proteinas || 0;
    const c100 = selectedDetectedFood.carbos || 0;
    const g100 = selectedDetectedFood.grasas || 0;

    const totalKcal = Math.round((kcal100 * grams) / 100);
    const totalP = ((p100 * grams) / 100).toFixed(1);
    const totalC = ((c100 * grams) / 100).toFixed(1);
    const totalG = ((g100 * grams) / 100).toFixed(1);

    document.getElementById('portionLivePreview').innerHTML = `
        ⚡ Consumo calculado (<strong>${grams}g</strong>): <strong class="text-orange" style="font-size:1.1rem;">${totalKcal} kcal</strong><br>
        🥩 Proteínas: <strong>${totalP}g</strong> | 🌾 Carbos: <strong>${totalC}g</strong> | 🥑 Grasas: <strong>${totalG}g</strong>
    `;
}

function closePortionModal() {
    document.getElementById('portionModal').classList.add('hidden');
    selectedDetectedFood = null;
}

async function confirmPortionLog() {
    if (!selectedDetectedFood) return;
    const grams = parseFloat(document.getElementById('portionGramsInput').value) || 100;

    try {
        await fetch(`/api/user/${currentUser}/log`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                alimento: selectedDetectedFood.alimento || selectedDetectedFood.nombre || 'Producto Escaneado',
                cantidad: grams,
                unidad: 'g',
                stats: selectedDetectedFood
            })
        });

        closePortionModal();
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        await loadUserData();
        switchTab('tab-dashboard');
    } catch (e) {
        alert('Error al registrar alimento en la jornada');
    }
}

async function savePortionFavorite() {
    if (!selectedDetectedFood) return;
    try {
        await fetch(`/api/user/${currentUser}/favorites`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                nombre: selectedDetectedFood.alimento || selectedDetectedFood.nombre || 'Favorito Escaneado',
                kcal: selectedDetectedFood.kcal || 0,
                proteinas: selectedDetectedFood.proteinas || 0,
                carbos: selectedDetectedFood.carbos || 0,
                grasas: selectedDetectedFood.grasas || 0
            })
        });
        alert('¡Producto guardado en tus favoritos!');
        await loadUserData();
    } catch (e) {
        alert('Error al guardar en favoritos');
    }
}

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

function resetPhotoUpload() {
    document.getElementById('aiPhotoInput').value = '';
    document.getElementById('imagePreview').src = '';
    document.getElementById('imagePreviewContainer').classList.add('hidden');
    document.getElementById('uploadText').textContent = 'Toca para abrir cámara o elegir foto';
    document.getElementById('btnSubmitAiPhoto').disabled = true;
}

// IA - Submit Foto (Plato o Etiqueta)
async function submitAiPhoto() {
    const imgSrc = document.getElementById('imagePreview').src;
    if (!imgSrc) return;

    const details = document.getElementById('aiPhotoDetails').value.trim();
    const btn = document.getElementById('btnSubmitAiPhoto');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analizando con Vision AI...';

    const endpoint = currentAiMode === 'label' ? '/api/ai/scan-label' : '/api/ai/scan-meal-photo';

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                image_base64: imgSrc,
                text_hint: details
            })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            if (currentAiMode === 'label') {
                openPortionModal(data.parsed);
            } else {
                displayAiResult(data.parsed);
            }
        } else {
            alert(data.message || 'No se pudo analizar la foto');
        }
    } catch (e) {
        alert('Error conectando con la IA de visión');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-sparkles"></i> Analizar Foto con IA';
    }
}

// IA - Submit Texto
async function submitAiText() {
    const text = document.getElementById('aiTextInput').value.trim();
    if (!text) return alert('Escribí una descripción.');

    const btn = document.getElementById('btnSubmitAiText');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Interpretando...';

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
            alert(data.message || 'No se pudo interpretar el texto');
        }
    } catch (e) {
        alert('Error consultando la IA');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Interpretar con IA';
    }
}

// Mostrar Resultado IA
function displayAiResult(parsed) {
    currentAiParsedFood = parsed;
    const box = document.getElementById('aiResultBox');
    const content = document.getElementById('aiResultContent');
    const badge = document.getElementById('aiConfidenceBadge');

    if (parsed.confianza) {
        badge.textContent = `Confianza: ${parsed.confianza}`;
    } else {
        badge.textContent = 'Interpretación IA';
    }

    content.innerHTML = `
        <h3 style="font-size:1.1rem; color:var(--text-primary); text-transform:capitalize; margin-bottom:4px;">${parsed.alimento || 'Plato analizado'}</h3>
        ${parsed.cantidad_estimada_g ? `<p style="color:var(--text-secondary); font-size:0.85rem; margin-bottom:8px;">Porción estimada: <strong>${parsed.cantidad_estimada_g}g</strong></p>` : ''}
        <div style="background:rgba(15,23,42,0.6); padding:10px; border-radius:10px; font-size:0.9rem;">
            🔥 Calorías: <strong class="text-orange">${Math.round(parsed.kcal || 0)} kcal</strong><br>
            🥩 Proteínas: <strong>${(parsed.proteinas || 0).toFixed(1)}g</strong> | 🌾 Carbos: <strong>${(parsed.carbos || 0).toFixed(1)}g</strong> | 🥑 Grasas: <strong>${(parsed.grasas || 0).toFixed(1)}g</strong>
        </div>
    `;

    box.classList.remove('hidden');
}

// Registrar resultado IA al día
async function logAiResult() {
    if (!currentAiParsedFood) return;
    try {
        await fetch(`/api/user/${currentUser}/log`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                alimento: currentAiParsedFood.alimento || 'Comida IA',
                cantidad: currentAiParsedFood.cantidad_estimada_g || 100,
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

// Guardar resultado IA como favorito
async function saveFavoriteFromAi() {
    if (!currentAiParsedFood) return;
    try {
        await fetch(`/api/user/${currentUser}/favorites`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                nombre: currentAiParsedFood.alimento || 'Favorito IA',
                kcal: currentAiParsedFood.kcal || 0,
                proteinas: currentAiParsedFood.proteinas || 0,
                carbos: currentAiParsedFood.carbos || 0,
                grasas: currentAiParsedFood.grasas || 0
            })
        });
        alert('¡Guardado en favoritos!');
        await loadUserData();
    } catch (e) {
        alert('Error al guardar en favoritos');
    }
}

// Log Favorito
async function logFavoriteItem(item) {
    openLogModal({
        alimento: item.nombre,
        kcal: item.kcal,
        proteinas: item.proteinas,
        carbos: item.carbos,
        grasas: item.grasas
    });
}

// Borrar Favorito
async function deleteFavoriteItem(nombre) {
    if (!confirm(`¿Eliminar "${nombre}" de favoritos?`)) return;
    try {
        await fetch(`/api/user/${currentUser}/favorites?nombre=${encodeURIComponent(nombre)}`, { method: 'DELETE' });
        await loadUserData();
    } catch (e) {
        alert('Error borrando favorito');
    }
}

// Recetas IA Heladera
async function generateFridgeRecipes() {
    const rawIngs = document.getElementById('fridgeIngredients').value.trim();
    if (!rawIngs) return alert('Ingresá al menos 1 o 2 ingredientes.');

    const ings = rawIngs.split(',').map(i => i.trim()).filter(Boolean);
    const container = document.getElementById('fridgeRecipesContainer');
    container.innerHTML = '<div class="placeholder-msg"><i class="fa-solid fa-spinner fa-spin text-green"></i> La IA está creando tus 3 recetas personalizadas...</div>';

    const kcalRem = currentUserData ? Math.max(200, currentUserData.meta_kcal - currentUserData.kcal) : 600;
    const protRem = currentUserData ? Math.max(10, currentUserData.meta_proteinas - currentUserData.proteinas) : 35;

    try {
        const res = await fetch('/api/ai/fridge-recipes', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ingredientes: ings, kcal_rem: kcalRem, prot_rem: protRem })
        });
        const data = await res.json();

        if (data.status === 'ok' && Array.isArray(data.recetas)) {
            container.innerHTML = data.recetas.map(rec => `
                <div class="recipe-item-card" style="flex-direction:column; align-items:flex-start; gap:8px;">
                    <div style="display:flex; justify-content:space-between; width:100%; align-items:center;">
                        <h4 style="color:var(--color-green); font-size:1rem;"><i class="fa-solid fa-utensils"></i> ${rec.titulo}</h4>
                        <span class="badge" style="color:var(--color-orange);">${Math.round(rec.kcal)} kcal</span>
                    </div>
                    <p style="font-size:0.82rem; color:var(--text-secondary);"><strong>Ingredientes:</strong> ${Array.isArray(rec.ingredientes) ? rec.ingredientes.join(', ') : rec.ingredientes}</p>
                    <p style="font-size:0.82rem; color:var(--text-muted); line-height:1.4;">${rec.instrucciones}</p>
                    <div style="display:flex; justify-content:space-between; width:100%; align-items:center; margin-top:6px; border-top:1px dashed var(--bg-card-border); padding-top:6px;">
                        <span style="font-size:0.8rem; color:var(--text-secondary);">P: ${rec.proteinas}g | C: ${rec.carbos}g | G: ${rec.grasas}g</span>
                        <button class="btn btn-success" style="padding:6px 12px; font-size:0.8rem;" onclick='openLogModal(${JSON.stringify({alimento: rec.titulo, kcal: rec.kcal, proteinas: rec.proteinas, carbos: rec.carbos, grasas: rec.grasas}).replace(/'/g, "&apos;")})'>
                            <i class="fa-solid fa-plus"></i> Usar Receta
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="placeholder-msg">No se pudieron generar recetas en este momento.</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="placeholder-msg">Error de conexión con la IA de cocina.</div>';
    }
}

// Eliminar Registro Historial Hoy
async function deleteHistoryItem(itemId) {
    if (!confirm('¿Eliminar esta comida del registro de hoy?')) return;
    try {
        await fetch(`/api/user/${currentUser}/history/${itemId}`, { method: 'DELETE' });
        await loadUserData();
    } catch (e) {
        alert('Error al eliminar');
    }
}

// Navegación Pestañas
function switchTab(tabId) {
    if (tabId !== 'tab-ai') {
        stopLiveScanner();
    }
    document.querySelectorAll('.tab-page').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.bottom-nav .nav-item').forEach(n => n.classList.remove('active'));

    const targetTab = document.getElementById(tabId);
    if (targetTab) targetTab.classList.add('active');

    const tabOrder = ['tab-dashboard', 'tab-search', 'tab-ai', 'tab-diary', 'tab-profile'];
    const navIndex = tabOrder.indexOf(tabId);
    if (navIndex !== -1) {
        const navItems = document.querySelectorAll('.bottom-nav .nav-item');
        if (navItems[navIndex]) navItems[navIndex].classList.add('active');
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Registrar Service Worker
function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(err => console.log('SW Note:', err));
    }
}
