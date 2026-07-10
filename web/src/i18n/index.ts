import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import fr from "./fr.json";

// FR/EN from day one (AudiGEO pattern) — everything through t(), enums included.
i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en } },
  lng: localStorage.getItem("oriflux.lang") ?? "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: "fr" | "en"): void {
  localStorage.setItem("oriflux.lang", lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
