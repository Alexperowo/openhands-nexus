import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import ruResources from "./locales/ru.json";
import { translationResources } from "@openhands/agent-canvas";

export const OPENHANDS_I18N_NAMESPACE = "openhands";

// Host-only keys (settings sections and labels Canvas does not have).
const nexusRu = { NEXUS$NAV_VOICE: "Голос", NEXUS$NAV_ACCESSIBILITY: "Доступность", NEXUS$SHOW_OPTIONS: "Показать варианты" };
const nexusEn = { NEXUS$NAV_VOICE: "Voice", NEXUS$NAV_ACCESSIBILITY: "Accessibility", NEXUS$SHOW_OPTIONS: "Show options" };

export const i18nInstance = i18next.createInstance();

// TalkBack picks the voice by the page language, and dates follow it (relative-time.ts).
// Subscribed before init: with inline resources init switches the language synchronously.
i18nInstance.on("languageChanged", (language) => { document.documentElement.lang = language; });

i18nInstance
  .use(initReactI18next)
  .init({
    lng: "ru",
    fallbackLng: "en",
    supportedLngs: ["ru", "en"],
    ns: [OPENHANDS_I18N_NAMESPACE],
    defaultNS: OPENHANDS_I18N_NAMESPACE,
    fallbackNS: OPENHANDS_I18N_NAMESPACE,
    resources: {
      ru: {
        [OPENHANDS_I18N_NAMESPACE]: { ...ruResources, ...nexusRu },
      },
      en: {
        [OPENHANDS_I18N_NAMESPACE]: { ...translationResources.en, ...nexusEn },
      },
    },
    interpolation: {
      escapeValue: false,
    },
  });

export default i18nInstance;
