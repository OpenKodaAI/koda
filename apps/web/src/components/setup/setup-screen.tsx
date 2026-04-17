"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { SetupFrame } from "@/components/setup/setup-frame";
import { SetupStepper } from "@/components/setup/setup-stepper";
import { StepFinishPlatform } from "@/components/setup/step-finish-platform";
import { StepLogin } from "@/components/setup/step-login";
import { StepRegisterOwner } from "@/components/setup/step-register-owner";
import { StepSetupCode } from "@/components/setup/step-setup-code";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  ControlPlaneAuthStatus,
  ControlPlaneOnboardingStatus,
} from "@/lib/control-plane";

type SetupStep = "setup_code" | "register_owner" | "login" | "finish_platform";

const STEP_ORDER: SetupStep[] = [
  "setup_code",
  "register_owner",
  "login",
  "finish_platform",
];

interface SetupScreenProps {
  authStatus: ControlPlaneAuthStatus | null;
  onboardingStatus: ControlPlaneOnboardingStatus | null;
}

export function SetupScreen({ authStatus, onboardingStatus }: SetupScreenProps) {
  const router = useRouter();
  const { t } = useAppI18n();
  const [, startTransition] = useTransition();

  const [registrationToken, setRegistrationToken] = useState("");

  const hasOperatorSession = Boolean(authStatus?.authenticated);
  const hasOwner = Boolean(authStatus?.has_owner ?? onboardingStatus?.has_owner);

  const currentStep: SetupStep = useMemo(() => {
    if (hasOperatorSession) return "finish_platform";
    if (!hasOwner && registrationToken.trim()) return "register_owner";
    if (!hasOwner) return "setup_code";
    return "login";
  }, [hasOperatorSession, hasOwner, registrationToken]);

  const stepIndex = STEP_ORDER.indexOf(currentStep);

  function refreshRoute() {
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <SetupFrame
      top={
        <div className="flex flex-col items-center gap-1">
          <SetupStepper total={STEP_ORDER.length} current={stepIndex} />
          <span className="text-[10.5px] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
            {t("setup.stepper.of", {
              current: stepIndex + 1,
              total: STEP_ORDER.length,
            })}
          </span>
        </div>
      }
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          {currentStep === "setup_code" ? (
            <StepSetupCode
              onExchanged={(token) => {
                setRegistrationToken(token);
              }}
              onRecoverySession={() => {
                refreshRoute();
              }}
            />
          ) : null}

          {currentStep === "register_owner" ? (
            <StepRegisterOwner
              registrationToken={registrationToken}
              initialEmail={onboardingStatus?.system.owner_email ?? null}
              initialDisplayName={onboardingStatus?.system.owner_name ?? null}
              onRegistered={() => {
                setRegistrationToken("");
                refreshRoute();
              }}
            />
          ) : null}

          {currentStep === "login" ? (
            <StepLogin
              initialIdentifier={authStatus?.operator?.username ?? null}
              recoveryAvailable={Boolean(authStatus?.recovery_available)}
              onSignedIn={() => {
                refreshRoute();
              }}
              onRecoveryRequested={() => {
                // Jump user back to setup code step with the recovery panel expanded
                // (handled implicitly by the first step's toggle button).
                setRegistrationToken("");
              }}
            />
          ) : null}

          {currentStep === "finish_platform" ? (
            <StepFinishPlatform
              initialStatus={onboardingStatus}
              authStatus={authStatus}
              onFinished={() => {
                router.replace("/");
                refreshRoute();
              }}
            />
          ) : null}
        </motion.div>
      </AnimatePresence>
    </SetupFrame>
  );
}
