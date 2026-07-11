import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import es from "./es.json";
import fr from "./fr.json";

export const LANGUAGES = ["fr", "en", "es"] as const;
export type Language = (typeof LANGUAGES)[number];

// FR/EN/ES (AudiGEO pattern) — everything through t(), enums included.
i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: fr },
    en: { translation: en },
    es: { translation: es },
  },
  lng: localStorage.getItem("oriflux.lang") ?? "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: Language): void {
  localStorage.setItem("oriflux.lang", lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
