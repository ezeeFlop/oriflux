import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { auth, loginWithGoogle } from "../lib/api";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: object) => void;
          renderButton: (parent: HTMLElement, options: object) => void;
        };
      };
    };
  }
}

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const buttonHost = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (response: { credential: string }) => {
          try {
            const { access_token } = await loginWithGoogle(response.credential);
            auth.token = access_token;
            navigate("/");
          } catch {
            setError(t("common.error"));
          }
        },
      });
      if (buttonHost.current) {
        window.google?.accounts.id.renderButton(buttonHost.current, {
          theme: "outline",
          size: "large",
          text: "continue_with",
        });
      }
    };
    document.head.appendChild(script);
    return () => script.remove();
  }, [navigate, t]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="rise w-full max-w-sm rounded-2xl border border-line bg-surface p-8 text-center shadow-[0_8px_30px_rgba(30,20,10,0.06)]">
        <svg viewBox="0 0 24 24" className="mx-auto h-10 w-10 text-flame" fill="currentColor">
          <path d="M4 3h13l-2.5 3.5L17 10H6v11a2 2 0 0 1-2-2V3z" />
        </svg>
        <h1 className="mt-3 font-display text-3xl font-bold tracking-tight">{t("app.name")}</h1>
        <p className="mt-1 text-sm text-ink-soft">{t("login.subtitle")}</p>
        <div className="mt-6 flex justify-center">
          {GOOGLE_CLIENT_ID ? (
            <div ref={buttonHost} />
          ) : (
            <p className="text-xs text-down">{t("login.missingClientId")}</p>
          )}
        </div>
        {error && <p className="mt-3 text-xs text-down">{error}</p>}
        <p className="mt-8 text-[11px] uppercase tracking-[0.2em] text-ink-soft">
          {t("app.tagline")}
        </p>
      </div>
    </div>
  );
}
