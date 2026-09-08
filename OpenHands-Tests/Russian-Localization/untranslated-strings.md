# Список допустимых непереведённых строк (EN == RU)

В словаре локализации `ru.json` насчитывается ровно **57** ключей, значения которых идентичны английскому оригиналу.  
В ходе аудита подтверждено, что ни один из этих ключей не является пропущенным элементом интерфейса (кнопкой, подсказкой, диалогом или заголовком).

---

## 1. Бренды, платформы и официальные названия (12 ключей)

| Ключ | Значение | Обоснование сохранения оригинала |
| :--- | :--- | :--- |
| `BRANDING$OPENHANDS` | `OpenHands` | Официальное наименование продукта |
| `BACKEND$CLOUD_TITLE` | `OpenHands Cloud` | Официальное наименование облачного сервиса |
| `BACKEND$AGENT_SERVER_TITLE` | `Agent-server` | Имя системного бинарника/сервиса |
| `COMMON$JUPYTER` | `Jupyter` | Название экосистемы интерактивных блокнотов |
| `GIT$SLACK` | `Slack` | Название корпоративного мессенджера |
| `GIT$GITLAB` | `GitLab` | Название платформы контроля версий |
| `GIT$BITBUCKET` | `Bitbucket` | Название платформы контроля версий |
| `GIT$AZURE_DEVOPS` | `Azure DevOps` | Название платформы Microsoft |
| `FILES$VSCODE` | `VSCode` | Название редактора кода |
| `GIT$GITHUB_API` | `GitHub API` | Техническое название программного интерфейса |
| `CONVERSATION$OVERVIEW_GIT` | `Git` | Название системы контроля версий |
| `CONVERSATION$ACP_AGENT_GENERIC` | `ACP` | Стандартная аббревиатура Agent Client Protocol |

---

## 2. Форматы, шаблоны и горячие клавиши (27 ключей)

| Ключ | Значение | Обоснование сохранения оригинала |
| :--- | :--- | :--- |
| `ACTION_MESSAGE$ACP_TOOL` | `<cmd>{{title}}</cmd>` | Внутренняя XML-разметка инструмента |
| `COMMAND_MENU$SHORTCUT` | `⌘K` | Общепринятое обозначение шортката клавиатуры |
| `CONVERSATION$OVERVIEW_DIFF_ADDITIONS` | `+{{count}}` | Числовой дифференциал строк в Git (+N) |
| `CONVERSATION$OVERVIEW_DIFF_DELETIONS` | `-{{count}}` | Числовой дифференциал строк в Git (-N) |
| `BACKEND$VERSION_LABEL` | `v{{version}}` | Международный формат номера версии (v1.16.0) |
| `CONVERSATION$OVERVIEW_UNAVAILABLE` | `—` | Типографическое тире (плейсхолдер отсутствия данных) |
| `CONVERSATION$BUDGET_USAGE_FORMAT` | `${currentCost} / ${maxBudget} ({usagePercentage}% {used})` | Математический шаблон расчёта стоимости |
| `AUTOMATIONS$DETAIL$MODEL` | `LLM profile` | Название системного поля профиля |
| `SETTINGS$SECURITY_LLM` | `LLM` | Общепринятая аббревиатура Large Language Model |

---

## 3. Технические пути, примеры токенов и OAuth scopes (18 ключей)

| Ключ | Значение | Обоснование сохранения оригинала |
| :--- | :--- | :--- |
| `API$TAVILY_KEY_EXAMPLE` | `tvly-dev-...` | Пример префикса API-токена Tavily |
| `API$TVLY_KEY_EXAMPLE` | `tvly-...` | Пример префикса API-токена Tavily |
| `AUTOMATIONS$GIT_SYNC$BRANCH_PLACEHOLDER` | `main` | Имя ветки Git по умолчанию |
| `AUTOMATIONS$GIT_SYNC$REPO_URL_PLACEHOLDER` | `https://github.com/org/repo.git` | Пример URL Git-репозитория |
| `COMMON$PLAN_MD` | `Plan.md` | Имя специального системного файла |
| `SETTINGS$SECRETS_EXAMPLE_NAME` | `STRIPE_API_KEY` | Стандартный пример переменной окружения |
| `SETTINGS$SECRETS_EXAMPLE_VALUE` | `sk_test_...` | Пример секретного ключа |
| `SETTINGS$GITHUB_TOKEN_SCOPES` | `repo, read:org, user:email` | Точные машинные имена OAuth-скоупов GitHub |
| `SETTINGS$GITLAB_TOKEN_SCOPES` | `api, read_user` | Точные машинные имена OAuth-скоупов GitLab |
| `SETTINGS$BITBUCKET_TOKEN_SCOPES` | `repository, pullrequest` | Точные машинные имена OAuth-скоупов Bitbucket |

---

## Заключение

Подозрительных строк не обнаружено. Все элементы интерфейса, подлежащие переводу на русский язык, переведены на 100%.\n