# Аудит, оптимизация и протокол полевых испытаний: Samsung Galaxy Z Fold 7

> **Дата фиксации:** 28 сентября 2026  
> **Устройство:** Samsung Galaxy Z Fold 7 (`SM-F966U1`, US Factory Unlocked, CSC `XAA`)  
> **ОС:** Android 16 / One UI 8.5  
> **Серийный номер:** `R3GYB0H0LZP`  
> **Оператор:** МегаФон Россия (`PLMN 25002`)  
> **Второй узел экосистемы:** Samsung Galaxy Tab S9 Ultra (`SM-X910`, `192.168.0.34:5555`)  
> **Исполнители:** Antigravity (Supervisor) + Qwen 27B (`:18000`, сессия `0996ab6e-c762-4c57-acb0-9648caf7b912`)

---

## 1. Исходное состояние и диагностика (Baseline)

### 1.1. Катастрофический жор батареи и срыв Deep Doze
* **Время работы в тесте:** ~10 часов.
* **Время нахождения в Deep Doze (глубокий сон процессора):** **всего 18 секунд** (~0.05% от времени сна). Процессор смартфона непрерывно бодрствовал в фоновом режиме на минимальных частотах, не переходя в энергосберегающие C-States.
* **Главные виновники утечек вейклоков (`PARTIAL_WAKE_LOCK`):**
  1. `com.samsung.android.smartsuggestions` (Подсказки One UI): **21.3 часа** суммарного удержания вейклока.
  2. `com.sec.android.daemonapp` (Samsung Weather / Погода): **18.5 часов** вейклока.
  3. `ru.crptech.mark` («Честный Знак»): **13.8 часов** вейклока (фоновый сокет, циклы синхронизации, трекинг).
  4. Фоновые демоны операторов США и аналитика: `com.sec.android.diagmonagent`, `com.sec.unifiedwfc`, `com.samsung.android.knox.analytics.uploader`, `com.google.android.as` (AiCore).

### 1.2. Инцидент с недозвоном (13:52 «Абонент вне зоны действия сети»)
* **Симптом:** При отличном приёме 4G и работающем интернете звонящие на МегаФон слышали сообщение о недоступности абонента.
* **Причина:** Приложение `Force LTE` выставило системный параметр `allowedNetworkTypesForReasons: user=4096` (`LTE Only`). На американской модели `SM-F966U1` в сети МегаФон профиль VoLTE не поддерживается нативно без операторского CSC. При входящем звонке сеть МегаФон запросила **CSFB (Circuit Switched FallBack)** в сеть 2G/3G (GSM), но модем из-за принудительного режима отмёл диапазон 2G (`CommandException: NO_NETWORK_FOUND`), сотовый стек перешёл в `OUT_OF_SERVICE`, и звонок сорвался.

### 1.3. Сбои Wi-Fi Calling (VoWiFi)
* Режим был выставлен в `wifi_call_preferred1=1` (`WIFI_PREFERRED`).
* Домашний GPON-роутер (`RT-5GPON-AAC8`) сбрасывал неактивные NAT-сессии IPsec по UDP 4500 каждые ~120 секунд в режиме сна смартфона, разрывая туннель до ePDG МегаФон при визуально активном Wi-Fi.

---

## 2. Выполненный комплекс работ (Remediation)

### 2.1. Изоляция и заморозка мусорных пакетов (Zero Uninstalls)
Все действия выполнены исключительно через `pm disable-user --user 0` без удаления пакетов и без сброса данных:
* **Волна 1 (14 пакетов):** Samsung Health, Forest (Digital Wellbeing), Facebook/Meta stubs (`facebook.katana`, `facebook.system`, `facebook.appmanager`, `facebook.services`), Bixby Agent & Service, Smart Switch, Samsung Kids.
* **Волна 2 (22 пакета):** Samsung Weather (`daemonapp`), Smart Suggestions, Galaxy Buds/Watch менеджера (фоновые демоны аксессуаров), Game Optimizing Service (GOS), Link to Windows (`yourphone`), AiCore, AdServices, Knox Analytics, CarrierDefaultApp, OMACPS.
* **Итого заморожено:** 36 паразитных фоновых пакетов.

### 2.2. Восстановление и строгое удушение «Честного Знака» (`ru.crptech.mark`)
* Пакет активирован обратно: `pm enable ru.crptech.mark`.
* Принудительно загнан в самый глубокий стэндбай: `am set-standby-bucket ru.crptech.mark 45` (`RESTRICTED`).
* Отозваны фоновые разрешения AppOps:
  ```bash
  appops set ru.crptech.mark RUN_IN_BACKGROUND ignore
  appops set ru.crptech.mark RUN_ANY_IN_BACKGROUND ignore
  appops set ru.crptech.mark WAKE_LOCK ignore
  ```
* Пользовательский сценарий сохранён: при открытии приложения камера сканирует QR/DataMatrix в реальном времени (`CAMERA: allow`), но в фоне приложение мгновенно засыпает и не держит процессор.

### 2.3. Защита ключевых сценариев пользователя
* **Аудиокниги и музыка по Bluetooth (JBL Sense Pro & Tour One M3):**
  - `ru.yandex.music` и `ru.litres.android` переведены в корзину `working_set` (20) / `active`.
  - Фоновое воспроизведение при заблокированном экране защищено, вейклоки аудиотракта разрешены.
* **Бесконтактная оплата NFC (SberPay, T-Pay / Т-Банк, Mir Pay):**
  - Приложения банков ограничены в фоне (`RESTRICTED`), но доступ к NFC и защищённому элементу Knox для оплаты на терминале сохранён.
* **Утилиты кастомизации Fine Lock:**
  - `yuh.yuh.finelock` и `SoundAssistant` проверены, работают без ограничений.

### 2.4. Стабилизация телефонии и сетей
* **Отключение 5G и приоритет 4G с гарантией голосового CSFB:**
  - Системная маска сети переключена на:
    ```bash
    cmd phone set-allowed-network-types-for-users -s 0 01001111101111111111
    ```
  - Диапазоны 5G (NR) полностью исключены (модем не тратит миллиамперы на поиск несуществующих вышек 5G).
  - Приоритет отдан 4G (LTE), при этом диапазоны 2G/3G (GSM/UMTS) открыты для мгновенного переключения голоса. Голосовой стек немедленно зарегистрировался на МегаФон (`IsVoiceCallAvailable: true`), все недошедшие SMS сразу доставлены.
* **Оптимизация Wi-Fi Calling:**
  - Переключено в режим приоритета сотовой сети (`settings put system wifi_call_preferred1 2`). Входящие звонки идут через вышку сотовой связи, а VoWiFi остаётся резервным каналом в зонах радиотени.

### 2.5. Samsung Continuity (MDEC) и многоустройственная связь
* Восстановлена служба доставки push-уведомлений Samsung: `com.sec.spp.push` (Samsung Push Service).
* Документирована механика **Knox Direct Boot (FBE)**: до первого ввода PIN-кода после перезагрузки раздел CE зашифрован, поэтому вызовы на планшет не транслируются. Как только экран разблокирован хотя бы один раз, MDEC переходит в `READYTOSYNC`, связь с Galaxy Tab S9 Ultra поднимается автоматически (`isAtLeast1SdReadyForCall=true`).

---

## 3. Протокол снятия контрольных данных через 1–2 недели

Когда закончится период повседневного использования, необходимо подключить Fold 7 по ADB и выполнить контрольный съем телеметрии.

### Контрольные метрики эффективности (KPI):
1. **Доля Deep Doze:** Целевое значение $\ge 70\text{--}80\%$ от общего времени сна экрана (было 0.05%).
2. **Фоновый разряд батареи:** Целевое значение $\le 0.5\text{--}1.0\%$ в час в режиме ожидания (ночью при выключенном экране).
3. **Вейклоки «Честного Знака»:** Суммарно не более 5 минут за сутки (было 13.8 часов).
4. **Стабильность голоса:** 0 пропущенных звонков с сообщением «вне зоны доступа» при наличии 4G/2G.
5. **Фоновое аудио:** 0 заиканий и выгрузок Яндекс Музыки и Литрес при длительном прослушивании в наушниках JBL.
6. **Трансляция звонков на Tab S9 Ultra:** Стабильный звонок и синхронизация SMS на планшете при разблокированном телефоне.

### Набор команд для автоматического съема отчета через 1–2 недели:
```powershell
# 1. Анализ статистики батареи и Doze
adb -s R3GYB0H0LZP shell dumpsys batterystats --checkin > K:\Project\scratch\battery_checkin_week2.txt
adb -s R3GYB0H0LZP shell dumpsys deviceidle stats

# 2. Проверка удержания вейклоков ключевыми процессами
adb -s R3GYB0H0LZP shell dumpsys batterystats | Select-String -Pattern "ru.crptech.mark|daemonapp|smartsuggestions|yandex.music|litres" -Context 2,2

# 3. Проверка корзин Standby
adb -s R3GYB0H0LZP shell "am get-standby-bucket ru.crptech.mark; am get-standby-bucket ru.yandex.music; am get-standby-bucket ru.litres.android"

# 4. Проверка состояния сотового стека и звонков
adb -s R3GYB0H0LZP shell "dumpsys telephony.registry | grep -E 'mCallState|mServiceState'"

# 5. Проверка статуса MDEC (связь с Tab S9 Ultra)
adb -s R3GYB0H0LZP shell dumpsys activity service com.samsung.android.mdecservice | Select-String -Pattern "ActiveServices|mEntitlementState"
```
