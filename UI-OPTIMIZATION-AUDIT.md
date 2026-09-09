# OpenHands Nexus — UI/UX Optimization Audit & Recommendations

**Дата:** 9 сентября 2026  
**Автор:** AI Audit System  
**Цель:** Улучшение UI Desktop и Mobile PWA — изящность, лаконичность, красота, удобство, скорость

---

## Executive Summary

Проведён детальный анализ UI-компонентов OpenHands Nexus:

| Файл | Строк | Статус | Оценка |
|------|-------|--------|--------|
| `working-profile-ui.css` | 471 | ✅ Синтаксис OK | 8.5/10 |
| `working-profile-ui.js` | 480 | ✅ Синтаксис OK | 8.0/10 |
| `voice-bridge.css` | 328 | ✅ Синтаксис OK | 8.5/10 |
| `voice-bridge.js` | 612 | ✅ Синтаксис OK | 8.0/10 |
| `mobile-pwa.css` | 79 | ✅ Синтаксис OK | 7.5/10 |

**Общая оценка:** 8.2/10 — хороший фундамент, есть возможности для значительных улучшений

---

## 1. ВИЗУАЛЬНАЯ ЭСТЕТИКА И ЛАКОНИЧНОСТЬ

### 1.1. Рабочий профиль (Working Profile Card)

**Текущее состояние:**
- Тёмная тема (#141418 фон, #3f3f46 границы)
- Крупные карточки с padding: 16px 20px
- Border-radius: 16px
- Box-shadow: 0 8px 24px rgba(0,0,0,0.6)
- Hover-эффект с подсветкой #6366f1

**Проблемы:**
1. **Избыточная визуальная плотность** — слишком много элементов в одной карточке:
   - Заголовок с иконкой ⚡
   - Бейдж (1/2/3 модели)
   - Индикатор синхронизации
   - Два селектора (профиль + reasoning)
   - Информационный блок с описанием
   - Динамическое описание режима

2. **Непоследовательные отступы** — gap: 14px в карточке, но gap: 10px в header, gap: 6px в field

3. **Слишком яркие hover-эффекты** — box-shadow: 0 8px 30px rgba(99,102,241,0.2) создаёт «визуальный шум»

**Рекомендации:**

#### HIGH-PRIORITY: Упрощение карточки рабочего профиля

```css
/* Предложение: более плоский, минималистичный дизайн */
.oh-wp-card {
    background: linear-gradient(180deg, #1a1a20 0%, #141418 100%);
    border: 1px solid #2a2a30;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    gap: 12px;
}

.oh-wp-card:hover,
.oh-wp-card:focus-within {
    border-color: #4a4a55;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    transform: translateY(-1px);
}
```

**Преимущества:**
- Меньше визуального шума
- Более современный «плоский» градиент
- Плавная микро-анимация вместо резкой подсветки
- Consistent spacing

#### MEDIUM-PRIORITY: Реструктуризация заголовка

**Текущий HTML:**
```html
<div class="oh-wp-header">
    <div class="oh-wp-title-group">
        <span class="oh-wp-icon">⚡</span>
        <span class="oh-wp-title">Рабочий профиль OpenHands</span>
    </div>
    <div class="oh-wp-header-badges">
        <span class="oh-wp-badge badge-3-models">3 МОДЕЛИ</span>
        <span class="oh-wp-sync-indicator">✓ Активно</span>
    </div>
</div>
```

**Предложение:** Удалить текстовый заголовок, оставить только контекстную информацию
```html
<div class="oh-wp-header-simplified">
    <div class="oh-wp-status-row">
        <span class="oh-wp-badge badge-3-models">3 МОДЕЛИ</span>
        <span class="oh-wp-profile-name">Team-Full</span>
        <span class="oh-wp-sync-dot" title="Синхронизировано"></span>
    </div>
</div>
```

**Преимущества:**
- Экономия ~40px вертикального пространства
- Название профиля важнее общего заголовка
- Индикатор синхронизации как компактная точка вместо текста

---

### 1.2. Селекторы (Select Controls)

**Текущее состояние:**
- min-height: 48px
- background: #1f1f23
- border: 2px solid #52525b
- padding: 10px 38px 10px 14px
- Custom arrow SVG

**Проблемы:**
1. **Стрелка селектора слишком мелкая** — 14px × 14px, fill: #a1a1aa (слабый контраст)
2. **Отсутствует визуальная обратная связь при выборе** — нет анимации открытия
3. **Опции в выпадающем списке не стилизованы** — браузерный default

**Рекомендации:**

#### HIGH-PRIORITY: Кастомный dropdown с анимацией

```css
.oh-wp-select-wrapper {
    position: relative;
    overflow: hidden;
    border-radius: 10px;
    transition: box-shadow 0.2s ease;
}

.oh-wp-select-wrapper::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    border-radius: 10px;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
    pointer-events: none;
    z-index: 2;
}

.oh-wp-select:focus + .oh-wp-select-arrow {
    animation: oh-arrow-bounce 0.3s ease;
}

@keyframes oh-arrow-bounce {
    0%, 100% { transform: translateY(-50%) rotate(0deg); }
    50% { transform: translateY(-50%) rotate(180deg); }
}
```

**Для опций селектора** (требует JS):
```javascript
// Заменить нативный <select> на кастомный dropdown
// с плавным появлением опций и hover-эффектами
```

---

### 1.3. Информационный блок (Info Box)

**Текущее состояние:**
```css
.oh-wp-info-box {
    background: #18181c;
    border: 1px solid #27272a;
    border-radius: 10px;
    padding: 12px 16px;
    gap: 6px;
}
```

**Проблема:** Выглядит как «приклеенный» блок, не интегрирован в общий дизайн

**Рекомендация: MEDIUM-PRIORITY**

Интегрировать информацию непосредственно в карточку без отдельной рамки:
```css
.oh-wp-info-integrated {
    margin-top: 4px;
    padding-top: 12px;
    border-top: 1px dashed rgba(255,255,255,0.1);
}

.oh-wp-desc-arch,
.oh-wp-desc-mode {
    font-size: 13px;
    color: #9ca3af;
    line-height: 1.5;
}

.oh-wp-highlight {
    color: #a5b4fc;
    font-weight: 600;
}
```

---

## 2. АНИМАЦИИ И МИКРОВЗАИМОДЕЙСТВИЯ

### 2.1. Текущие анимации

| Анимация | Длительность | Тип | Оценка |
|----------|--------------|-----|--------|
| `oh-wp-fade-in` | 0.15s | fade + slide | ✅ Хорошо |
| `oh-mic-pulse` | 1.2s | scale + shadow | ✅ Хорошо |
| `oh-popover-in` | 0.15s | fade + slide | ✅ Хорошо |
| Hover border-color | 0.2s | color | ✅ Хорошо |

**Проблема:** Отсутствуют анимации для:
- Переключения селекторов
- Изменения состояния синхронизации
- Появления новых сообщений
- Перехода между страницами SPA

### 2.2. Рекомендации по анимациям

#### HIGH-PRIORITY: Плавное переключение профилей

```css
/* Добавление класса при изменении селектора */
.oh-wp-card.is-changing {
    animation: oh-wp-pulse-change 0.4s ease;
}

@keyframes oh-wp-pulse-change {
    0% { transform: scale(1); }
    50% { transform: scale(1.02); box-shadow: 0 4px 20px rgba(99,102,241,0.3); }
    100% { transform: scale(1); }
}
```

```javascript
// В working-profile-ui.js, после switchProfile():
function animateProfileChange() {
    const card = document.querySelector('.oh-wp-card');
    if (card) {
        card.classList.add('is-changing');
        setTimeout(() => card.classList.remove('is-changing'), 400);
    }
}
```

#### MEDIUM-PRIORITY: Индикатор загрузки с анимацией

Заменить текстовое «Сохранение...» на анимированный spinner:
```css
.oh-wp-sync-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255,255,255,0.2);
    border-top-color: #22c55e;
    border-radius: 50%;
    animation: oh-spin 0.8s linear infinite;
}

@keyframes oh-spin {
    to { transform: rotate(360deg); }
}
```

---

## 3. MOBILE PWA — СПЕЦИФИЧЕСКИЕ УЛУЧШЕНИЯ

### 3.1. Текущее состояние mobile-pwa.css

**Строк:** 79  
**Покрытие:** Базовые safe-area insets, touch targets, responsive tables

**Проблемы:**
1. **Отсутствует адаптация Working Profile Card для мобильных** — используется тот же размер шрифта и отступы
2. **Нет оптимизации для ландшафтного режима**
3. **Не учитывается динамический island / вырезы камер**
4. **Отсутствует поддержка жестов навигации**

### 3.2. Рекомендации

#### HIGH-PRIORITY: Мобильная версия карточки профиля

```css
@media (max-width: 768px) {
    .oh-wp-card {
        padding: 12px;
        gap: 10px;
        border-radius: 10px;
    }
    
    .oh-wp-title {
        font-size: 14px;
        font-weight: 600;
    }
    
    .oh-wp-badge {
        padding: 2px 8px;
        font-size: 10px;
    }
    
    /* Скрывать подробное описание на мобильных */
    .oh-wp-desc-mode {
        display: none;
    }
    
    .oh-wp-desc-arch {
        font-size: 12px;
        max-lines: 2;
        overflow: hidden;
        text-overflow: ellipsis;
    }
}

@media (max-width: 480px) {
    /* Очень маленькие экраны */
    .oh-wp-controls-grid {
        grid-template-columns: 1fr;
        gap: 8px;
    }
    
    .oh-wp-select {
        min-height: 44px;
        font-size: 15px;
        padding: 8px 32px 8px 12px;
    }
}
```

#### MEDIUM-PRIORITY: Ландшафтный режим

```css
@media (orientation: landscape) and (max-height: 500px) {
    .oh-wp-card {
        flex-direction: row;
        flex-wrap: wrap;
        padding: 10px;
    }
    
    .oh-wp-header {
        width: 100%;
        margin-bottom: 8px;
    }
    
    .oh-wp-controls-grid {
        grid-template-columns: 1fr 1fr;
        gap: 8px;
    }
    
    .oh-wp-info-box {
        display: none; /* Экономия места */
    }
}
```

#### LOW-PRIORITY: Поддержка жестов навигации

```css
/* Предотвращение случайного свайпа назад при скролле */
.oh-wp-container {
    touch-action: pan-y pinch-zoom;
}

/* Визуальная подсказка для свайпа вверх/вниз */
.oh-wp-scroll-hint {
    position: absolute;
    bottom: 8px;
    left: 50%;
    transform: translateX(-50%);
    width: 40px;
    height: 4px;
    background: rgba(255,255,255,0.3);
    border-radius: 2px;
    animation: oh-scroll-hint 1.5s ease-in-out infinite;
}

@keyframes oh-scroll-hint {
    0%, 100% { opacity: 0.3; transform: translateX(-50%) translateY(0); }
    50% { opacity: 0.8; transform: translateX(-50%) translateY(4px); }
}
```

---

## 4. ГОЛОСОВОЙ ИНТЕРФЕЙС (VOICE BRIDGE)

### 4.1. Floating Pill — текущее состояние

**Расположение:** bottom-left, fixed  
**Размер:** padding: 6px 14px, font-size: 13px  
**Анимация:** oh-mic-pulse при recording/speaking

**Проблемы:**
1. **Может перекрывать важные элементы** на маленьких экранах
2. **Отсутствует возможность перетаскивания** — зафиксирован в одном месте
3. **Не исчезает автоматически** после бездействия
4. **Нет тактильной обратной связи** при клике (только при recording)

### 4.2. Рекомендации

#### HIGH-PRIORITY: Drag-to-reposition для pill

```javascript
// Добавить возможность перетаскивания
let isDragging = false;
let dragOffset = { x: 0, y: 0 };

pill.addEventListener('mousedown', startDrag);
pill.addEventListener('touchstart', startDrag, { passive: false });

function startDrag(e) {
    if (e.target.closest('.oh-voice-popover')) return;
    isDragging = true;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const rect = pill.getBoundingClientRect();
    dragOffset.x = clientX - rect.left;
    dragOffset.y = clientY - rect.top;
    pill.style.transition = 'none';
}

document.addEventListener('mousemove', onDrag);
document.addEventListener('touchmove', onDrag, { passive: false });

function onDrag(e) {
    if (!isDragging) return;
    e.preventDefault();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    pill.style.left = (clientX - dragOffset.x) + 'px';
    pill.style.bottom = 'auto';
    pill.style.top = (clientY - dragOffset.y) + 'px';
}

document.addEventListener('mouseup', endDrag);
document.addEventListener('touchend', endDrag);

function endDrag() {
    isDragging = false;
    pill.style.transition = 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)';
    // Сохранить позицию в localStorage
    localStorage.setItem('oh_voice_pill_x', pill.style.left);
    localStorage.setItem('oh_voice_pill_y', pill.style.top);
}
```

#### MEDIUM-PRIORITY: Auto-hide после бездействия

```javascript
let pillHideTimeout;

function showPill() {
    pill.style.opacity = '1';
    pill.style.pointerEvents = 'auto';
    clearTimeout(pillHideTimeout);
    pillHideTimeout = setTimeout(hidePill, 8000);
}

function hidePill() {
    if (isRecording || isSpeaking) return;
    pill.style.opacity = '0.3';
    pill.style.pointerEvents = 'none';
}

// Показывать при взаимодействии
document.addEventListener('mousemove', showPill);
document.addEventListener('touchstart', showPill);
```

---

## 5. ACCESSIBILITY — ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ

### 5.1. Текущее соответствие WCAG

| Критерий | Статус | Примечание |
|----------|--------|------------|
| 2.5.5 Target Size (44px) | ✅ | Все кнопки ≥44px |
| 2.5.8 Target Size (Minimum) | ✅ | Минимум 24px² |
| 1.4.3 Contrast (AA) | ✅ | Высокий контраст |
| 4.1.2 Name, Role, Value | ⚠️ | Некоторые элементы без aria-label |
| 2.1.1 Keyboard | ✅ | Tab navigation работает |
| 1.3.1 Info and Relationships | ⚠️ | Не все labels связаны явно |

### 5.2. Рекомендации

#### HIGH-PRIORITY: Добавить ARIA-live для статусов

```html
<!-- Добавить в working-profile-ui.js -->
<div id="oh-wp-status-announcer" 
     aria-live="polite" 
     aria-atomic="true" 
     class="sr-only">
</div>
```

```css
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}
```

```javascript
// Объявлять изменения для скринридеров
function announceStatus(message) {
    const announcer = document.getElementById('oh-wp-status-announcer');
    if (announcer) {
        announcer.textContent = message;
        setTimeout(() => announcer.textContent = '', 1000);
    }
}

// Использовать при переключении профиля
announceStatus(`Выбран профиль: ${currentWp.name}, режим: ${activeModeObj.label}`);
```

#### MEDIUM-PRIORITY: Улучшить focus indicators

```css
/* Текущий focus: box-shadow: 0 0 0 3px rgba(99,102,241,0.35) */
/* Предложение: более заметный outline с анимацией */

.oh-wp-select:focus,
.oh-wp-new-chat-btn:focus,
#oh-composer-mic-btn:focus-visible {
    outline: 3px solid #a5b4fc;
    outline-offset: 2px;
    box-shadow: 0 0 0 5px rgba(165, 180, 252, 0.4);
    animation: oh-focus-ring 0.3s ease;
}

@keyframes oh-focus-ring {
    0% { outline-offset: 0px; }
    100% { outline-offset: 2px; }
}
```

---

## 6. ПРОИЗВОДИТЕЛЬНОСТЬ

### 6.1. Выявленные проблемы

#### CRITICAL: MutationObserver без debounce

**Файл:** `working-profile-ui.js`, строка 443  
**Код:**
```javascript
const observer = new MutationObserver(() => {
    const hasInput = document.querySelector(".chat-input");
    const existingPanel = document.getElementById("oh-working-profile-container");
    const routeChanged = lastRenderedRoute !== isConversationPage();

    if (hasInput && (!existingPanel || routeChanged)) {
        renderUI();
    } else if (existingPanel && isConversationPage()) {
        renderUI();
    }
});

observer.observe(document.body, { childList: true, subtree: true });
```

**Проблема:** Observer вызывается при КАЖДОМ изменении DOM, что может происходить сотни раз в секунду при активной работе агента (печать кода, обновление статуса, progress bars).

**Решение: HIGH-PRIORITY**

```javascript
// Debounce утилита
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Оптимизированный observer
const debouncedRenderUI = debounce(renderUI, 150);

const observer = new MutationObserver((mutationsList) => {
    // Проверять только релевантные изменения
    let shouldRender = false;
    
    for (const mutation of mutationsList) {
        if (mutation.type === 'childList') {
            const hasChatInput = mutation.target.querySelector?.('.chat-input');
            if (hasChatInput) {
                shouldRender = true;
                break;
            }
        }
    }
    
    if (shouldRender) {
        const hasInput = document.querySelector(".chat-input");
        const existingPanel = document.getElementById("oh-working-profile-container");
        const routeChanged = lastRenderedRoute !== isConversationPage();
        
        if (hasInput && (!existingPanel || routeChanged)) {
            debouncedRenderUI();
        } else if (existingPanel && isConversationPage()) {
            debouncedRenderUI();
        }
    }
});
```

**Ожидаемый эффект:** Снижение нагрузки на CPU на 80–90% при активном обновлении UI агентом.

---

#### HIGH-PRIORITY: setInterval 3000ms без паузы

**Файл:** `working-profile-ui.js`, строка 459  
**Код:**
```javascript
setInterval(() => {
    loadWorkingProfiles(true);
}, 3000);
```

**Проблема:** Запросы выполняются даже когда вкладка неактивна или пользователь не взаимодействует с интерфейсом.

**Решение:**
```javascript
// Оптимизированный polling
let syncInterval;

function startSyncPolling() {
    stopSyncPolling();
    syncInterval = setInterval(() => {
        // Не синхронизировать если вкладка неактивна
        if (document.hidden) return;
        // Не синхронизировать если идёт запись/воспроизведение
        if (isRecording || isSpeaking) return;
        loadWorkingProfiles(true);
    }, 3000);
}

function stopSyncPolling() {
    if (syncInterval) clearInterval(syncInterval);
}

// Пауза при потере фокуса
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopSyncPolling();
    } else {
        startSyncPolling();
        loadWorkingProfiles(true); // Немедленная синхронизация при возврате
    }
});

window.addEventListener('blur', stopSyncPolling);
window.addEventListener('focus', startSyncPolling);
```

---

#### MEDIUM-PRIORITY: Избыточные fetch-запросы

**Проблема:** `loadWorkingProfiles()` вызывается из 4 мест:
1. `init()` при загрузке
2. `setInterval` каждые 3 секунды
3. `window.focus` event
4. После успешного `switchProfile()`

**Решение:** Кэширование с TTL
```javascript
const CACHE_TTL = 2000; // 2 секунды
let lastFetchTime = 0;
let cachedData = null;
let pendingRequest = null;

async function loadWorkingProfiles(silent = false, force = false) {
    const now = Date.now();
    
    // Вернуть кэш если он свежий и не форсировано обновление
    if (!force && cachedData && (now - lastFetchTime) < CACHE_TTL) {
        return cachedData;
    }
    
    // Отменить предыдущий запрос если ещё выполняется
    if (pendingRequest) {
        // pendingRequest.abort(); // если используется AbortController
    }
    
    try {
        pendingRequest = fetch(API_URL, {
            headers: { "Cache-Control": "no-cache" }
        });
        
        const resp = await pendingRequest;
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        
        const data = await resp.json();
        cachedData = data;
        lastFetchTime = now;
        pendingRequest = null;
        
        // ... остальная логика
    } catch (err) {
        pendingRequest = null;
        // ... обработка ошибки
    }
}
```

---

## 7. VISUAL HIERARCHY И КОМПОЗИЦИЯ

### 7.1. Проблема: Отсутствие явной визуальной иерархии

**Текущее состояние:** Все элементы имеют схожий визуальный вес:
- Заголовок: 18px, 700 weight
- Бейджи: 13px, 800 weight, яркие цвета
- Селекторы: 16px, 600 weight
- Описание: 15px, 500 weight

**Результат:** Пользователь не понимает, куда смотреть в первую очередь

### 7.2. Рекомендация: Переработать иерархию

```css
/* Новая иерархия: Профиль → Reasoning → Описание */

/* 1. Главный акцент: выбранный профиль */
.oh-wp-select-profile {
    font-size: 17px;
    font-weight: 700;
    background: linear-gradient(180deg, #252530 0%, #1f1f23 100%);
    border-color: #6366f1;
}

/* 2. Вторичный акцент: режим рассуждения */
.oh-wp-select-reasoning {
    font-size: 15px;
    font-weight: 600;
    background: #1f1f23;
    border-color: #52525b;
}

/* 3. Третичный: описание (приглушённое) */
.oh-wp-desc-arch {
    font-size: 13px;
    color: #9ca3af;
    font-weight: 400;
}

.oh-wp-desc-mode {
    font-size: 12px;
    color: #6b7280;
    font-style: italic;
}
```

---

## 8. ЦВЕТОВАЯ ПАЛИТРА — ПРЕДЛОЖЕНИЯ

### 8.1. Текущая палитра

| Элемент | Цвет | Назначение |
|---------|------|------------|
| Фон карточки | #141418 | Основной |
| Границы | #3f3f46 | Разделители |
| Акцент | #6366f1 | Indigo (hover, focus) |
| Текст | #ffffff | Заголовки |
| Текст вторичный | #a1a1aa | Описания |
| Успех | #22c55e | Синхронизация |
| Ошибка | #ef4444 | Recording, errors |

### 8.2. Рекомендация: Расширенная палитра для состояний

```css
:root {
    /* Основные цвета */
    --oh-bg-primary: #141418;
    --oh-bg-secondary: #1f1f23;
    --oh-bg-tertiary: #27272a;
    
    /* Границы */
    --oh-border-default: #3f3f46;
    --oh-border-hover: #52525b;
    --oh-border-focus: #6366f1;
    
    /* Акценты */
    --oh-accent-primary: #6366f1;      /* Indigo 500 */
    --oh-accent-light: #a5b4fc;        /* Indigo 300 */
    --oh-accent-dark: #4338ca;         /* Indigo 700 */
    
    /* Статусы */
    --oh-status-success: #10b981;      /* Emerald 500 */
    --oh-status-warning: #f59e0b;      /* Amber 500 */
    --oh-status-error: #ef4444;        /* Red 500 */
    --oh-status-info: #38bdf8;         /* Sky 400 */
    
    /* Текст */
    --oh-text-primary: #ffffff;
    --oh-text-secondary: #d4d4d8;
    --oh-text-tertiary: #a1a1aa;
    --oh-text-muted: #71717a;
}
```

**Преимущества:**
- Консистентность across всех компонентов
- Легче поддерживать и изменять
- Темизация через замену переменных

---

## 9. DARK MODE ENHANCEMENTS

### 9.1. Проблема: Слишком тёмная тема может утомлять глаза

**Текущий фон:** #141418 (очень тёмный, почти чёрный)  
**Контраст:** Высокий, но может быть утомительным при длительном использовании

### 9.2. Рекомендация: Добавить вариант «Soft Dark»

```css
/* Опционально: более мягкая тёмная тема */
[data-theme="soft-dark"] .oh-wp-card {
    background: linear-gradient(180deg, #2a2a35 0%, #25252e 100%);
    border-color: #3a3a45;
}

[data-theme="soft-dark"] .oh-wp-select {
    background: #2d2d35;
    color: #f0f0f5;
}

[data-theme="soft-dark"] .oh-wp-info-box {
    background: #25252e;
    border-color: #353540;
}
```

**Переключатель тем:**
```html
<button id="oh-theme-toggle" aria-label="Переключить тему">
    🌙
</button>
```

```javascript
document.getElementById('oh-theme-toggle').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'soft-dark' ? 'default' : 'soft-dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('oh_theme', next);
});
```

---

## 10. PRIORITIZATION MATRIX

| ID | Улучшение | Приоритет | Сложность | Эффект |
|----|-----------|-----------|-----------|--------|
| **UI-01** | Debounce MutationObserver | 🔴 HIGH | Низкая | ⭐⭐⭐⭐⭐ Производительность |
| **UI-02** | Оптимизация polling (visibility API) | 🔴 HIGH | Средняя | ⭐⭐⭐⭐ Производительность |
| **UI-03** | Упрощение дизайна карточки | 🔴 HIGH | Средняя | ⭐⭐⭐⭐ Визуал |
| **UI-04** | Кастомный dropdown с анимацией | 🟡 MEDIUM | Высокая | ⭐⭐⭐ UX |
| **UI-05** | Мобильная адаптация карточки | 🔴 HIGH | Низкая | ⭐⭐⭐⭐ Mobile UX |
| **UI-06** | ARIA-live announcer | 🔴 HIGH | Низкая | ⭐⭐⭐⭐ Accessibility |
| **UI-07** | Drag-to-reposition для voice pill | 🟡 MEDIUM | Средняя | ⭐⭐⭐ UX |
| **UI-08** | Auto-hide voice pill | 🟡 MEDIUM | Низкая | ⭐⭐ Чистота UI |
| **UI-09** | Focus ring enhancement | 🟡 MEDIUM | Низкая | ⭐⭐⭐ Accessibility |
| **UI-10** | Цветовая палитра через CSS vars | 🟢 LOW | Средняя | ⭐⭐ Поддерживаемость |
| **UI-11** | Soft dark theme toggle | 🟢 LOW | Средняя | ⭐⭐ Комфорт |
| **UI-12** | Ландшафтный режим | 🟢 LOW | Низкая | ⭐⭐ Mobile edge case |

---

## 11. РЕКОМЕНДУЕМЫЙ ПЛАН РЕАЛИЗАЦИИ

### Спринт 1: Критические улучшения производительности (2-3 часа)
1. ✅ UI-01: Debounce MutationObserver
2. ✅ UI-02: Optimized polling с visibility API
3. ✅ UI-06: ARIA-live announcer

### Спринт 2: Визуальные улучшения Desktop (3-4 часа)
1. ✅ UI-03: Упрощение дизайна карточки
2. ✅ UI-04: Кастомный dropdown (опционально)
3. ✅ UI-10: CSS variables palette

### Спринт 3: Mobile оптимизация (2-3 часа)
1. ✅ UI-05: Мобильная адаптация карточки
2. ✅ UI-07: Drag-to-reposition voice pill
3. ✅ UI-12: Ландшафтный режим

### Спринт 4: Accessibility polish (1-2 часа)
1. ✅ UI-09: Enhanced focus rings
2. ✅ UI-08: Auto-hide voice pill
3. ✅ UI-11: Soft dark theme (опционально)

---

## 12. ЗАКЛЮЧЕНИЕ

**Текущее состояние UI:** 8.2/10 — хороший, функциональный интерфейс с высоким соответствием accessibility

**Потенциал после оптимизаций:** 9.5/10 — изящный, быстрый, профессиональный продукт

**Ключевые находки:**
1. **MutationObserver без debounce** — критическая проблема производительности
2. **Постоянный polling без паузы** — напрасная трата ресурсов
3. **Избыточная визуальная плотность** — можно упростить без потери функциональности
4. **Недостаточная мобильная адаптация** — требует внимания для PWA
5. **ARIA-live отсутствует** — важно для пользователей скринридеров

**Не рекомендуется менять:**
- ❌ Высокий контраст — отлично для слабовидящих
- ❌ Крупные touch targets (44px+) — идеально соответствует WCAG
- ❌ Dual-engine TTS architecture — гибкость важнее упрощения
- ❌ Working Profile инварианты — архитектурная целостность

---

**Следующие шаги:**
1. Обсудить приоритеты с командой
2. Начать со Спринта 1 (производительность)
3. Тестировать на физическом Android (Samsung Tab S9 Ultra)
4. Задокументировать изменения в CHANGELOG.md
