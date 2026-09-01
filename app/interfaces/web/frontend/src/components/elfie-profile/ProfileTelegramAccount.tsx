import { Button } from "@/components/ui/button"
import { Check, Copy, ExternalLink, MoreHorizontal } from "lucide-react"
import { DropdownMenu } from "radix-ui"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  configureTelegramAccount,
  createTelegramPairingSession,
  disconnectTelegramAccount,
  type TelegramAccount,
  type TelegramPairingSession,
} from "../../api/client"
import { ConfirmDialog } from "../ConfirmDialog"
import { ManageDialog } from "../ManageDialog"
import { TextField } from "../TextField"

type ProfileTelegramAccountProps = {
  readonly account: TelegramAccount | null
  readonly accountError?: string | null
  readonly accountLoading?: boolean
  readonly csrfToken?: string | undefined
  readonly elfieId: string
  readonly elfieName: string
  readonly onAccountChange?: ((account: TelegramAccount) => void) | undefined
  readonly onRefresh?: (() => Promise<void>) | undefined
}

type BusyAction = "configure" | "pairing" | "disconnect" | "refresh" | null
type SetupStep = 1 | 2 | 3

const SETUP_STEPS: readonly SetupStep[] = [1, 2, 3]
const TELEGRAM_POLL_INTERVAL_MS = 2_000

export function ProfileTelegramAccount({
  account,
  accountError = null,
  accountLoading = false,
  csrfToken,
  elfieId,
  elfieName,
  onAccountChange,
  onRefresh,
}: ProfileTelegramAccountProps) {
  const { t } = useTranslation("chat")
  const [currentAccount, setCurrentAccount] = useState<TelegramAccount | null>(account)
  const [botToken, setBotToken] = useState("")
  const [pairing, setPairing] = useState<TelegramPairingSession | null>(null)
  const [busyAction, setBusyAction] = useState<BusyAction>(null)
  const [error, setError] = useState<string | null>(null)
  const [copiedValue, setCopiedValue] = useState<string | null>(null)
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [setupOpen, setSetupOpen] = useState(false)
  const [setupStep, setSetupStep] = useState<SetupStep>(1)

  useEffect(() => {
    setCurrentAccount(account)
  }, [account])

  useEffect(() => {
    setBotToken("")
    setPairing(null)
    setError(null)
    setCopiedValue(null)
    setSetupOpen(false)
    setSetupStep(1)
  }, [elfieId])

  const editable = csrfToken !== undefined && csrfToken !== ""
  const busy = busyAction !== null
  const state = currentAccount?.state ?? "unconfigured"
  const suggestedUsername = buildSuggestedUsername(elfieName, elfieId)
  const botHref = currentAccount?.bot_username ? `https://t.me/${currentAccount.bot_username}` : null
  const stepLabels: Record<SetupStep, string> = {
    1: t("profile.private.telegram.steps.create"),
    2: t("profile.private.telegram.steps.token"),
    3: t("profile.private.telegram.steps.bind"),
  }

  async function createPairing(): Promise<void> {
    if (!editable || csrfToken === undefined) return
    setBusyAction("pairing")
    setError(null)
    try {
      setPairing(await createTelegramPairingSession(elfieId, csrfToken))
    } catch (reason: unknown) {
      setError(reason instanceof Error && reason.message ? reason.message : t("profile.private.telegram.pairingError"))
    } finally {
      setBusyAction(null)
    }
  }

  const openSetup = (step: SetupStep = state === "waiting_pairing" ? 3 : 1): void => {
    setSetupStep(step)
    setBotToken("")
    setPairing(null)
    setError(null)
    setSetupOpen(true)
    if (step === 3 && state !== "active") void createPairing()
  }

  const closeSetup = (open: boolean): void => {
    setSetupOpen(open)
    if (open) return
    setBotToken("")
    setPairing(null)
    setError(null)
    setCopiedValue(null)
  }

  const goBack = (): void => {
    setError(null)
    if (setupStep === 1) {
      closeSetup(false)
      return
    }
    setSetupStep(setupStep === 3 ? 2 : 1)
  }

  const copyText = async (value: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value)
      setCopiedValue(value)
    } catch {
      setError(t("profile.private.telegram.copyError"))
    }
  }

  const configure = async (): Promise<void> => {
    if (!editable || csrfToken === undefined || !botToken.trim()) return
    setBusyAction("configure")
    setError(null)
    try {
      const updated = await configureTelegramAccount(elfieId, botToken.trim(), csrfToken)
      setCurrentAccount(updated)
      setBotToken("")
      setPairing(null)
      onAccountChange?.(updated)
      setSetupStep(3)
      if (updated.state !== "active") {
        setBusyAction("pairing")
        try {
          setPairing(await createTelegramPairingSession(elfieId, csrfToken))
        } catch (reason: unknown) {
          setError(reason instanceof Error && reason.message ? reason.message : t("profile.private.telegram.pairingError"))
        }
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error && reason.message ? reason.message : t("profile.private.telegram.configureError"))
    } finally {
      setBusyAction(null)
    }
  }

  const refresh = async (): Promise<void> => {
    if (onRefresh === undefined) return
    setBusyAction("refresh")
    setError(null)
    try {
      await onRefresh()
    } catch (reason: unknown) {
      setError(reason instanceof Error && reason.message ? reason.message : t("profile.private.telegram.refreshError"))
    } finally {
      setBusyAction(null)
    }
  }

  const disconnect = async (): Promise<void> => {
    if (!editable || csrfToken === undefined) return
    setBusyAction("disconnect")
    setError(null)
    try {
      const updated = await disconnectTelegramAccount(elfieId, csrfToken)
      setCurrentAccount(updated)
      setPairing(null)
      setConfirmDisconnect(false)
      onAccountChange?.(updated)
    } catch (reason: unknown) {
      setError(reason instanceof Error && reason.message ? reason.message : t("profile.private.telegram.disconnectError"))
    } finally {
      setBusyAction(null)
    }
  }

  useEffect(() => {
    if (!setupOpen || setupStep !== 3 || state !== "waiting_pairing" || onRefresh === undefined) return
    let inFlight = false
    const poll = async (): Promise<void> => {
      if (inFlight) return
      inFlight = true
      try {
        await onRefresh()
      } catch {
        // Polling stays quiet; the owner can retry from the account card if the connection fails.
      } finally {
        inFlight = false
      }
    }
    void poll()
    const timer = window.setInterval(() => { void poll() }, TELEGRAM_POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [onRefresh, setupOpen, setupStep, state])

  if (accountLoading) {
    return <p className="profile-private-module__empty" role="status">{t("profile.private.telegram.loading")}</p>
  }

  if (accountError && currentAccount === null) {
    return <div className="profile-private-telegram">
      <p className="profile-private-telegram__notice profile-private-telegram__notice--error" role="alert">{accountError}</p>
      {onRefresh !== undefined ? <Button disabled={busy} onClick={() => { void refresh() }} type="button" variant="ghost">
        {busyAction === "refresh" ? t("profile.private.telegram.retrying") : t("profile.private.telegram.retry")}
      </Button> : null}
    </div>
  }

  const setupDialog = <ManageDialog
    contentClassName="manage-dialog--telegram"
    onOpenChange={closeSetup}
    open={setupOpen}
    title={t("profile.private.telegram.setupTitle")}
  >
    <ol aria-label={t("profile.private.telegram.stepsLabel")} className="profile-private-telegram__steps">
      {SETUP_STEPS.map((step) => (
        <li
          aria-current={setupStep === step ? "step" : undefined}
          className={setupStep === step ? "profile-private-telegram__step-marker profile-private-telegram__step-marker--active" : setupStep > step ? "profile-private-telegram__step-marker profile-private-telegram__step-marker--complete" : "profile-private-telegram__step-marker"}
          key={step}
        >
          <span>{setupStep > step ? <Check aria-hidden="true" /> : step}</span>
          <small>{stepLabels[step]}</small>
        </li>
      ))}
    </ol>

    <section className="profile-private-telegram__wizard-step" aria-live="polite">
      {setupStep === 1 ? <ol className="profile-private-telegram__checklist">
        <li>
          <span>{t("profile.private.telegram.stepOne.openBefore")}{" "}<a href="https://t.me/BotFather" rel="noreferrer" target="_blank">@BotFather<ExternalLink aria-hidden="true" /></a>{t("profile.private.telegram.stepOne.openAfter")}</span>
        </li>
        <li>
          <span>{t("profile.private.telegram.stepOne.send")}{" "}</span>
          <CopyValueButton copied={copiedValue === "/newbot"} label={t("profile.private.telegram.copy", { value: "/newbot" })} onCopy={() => { void copyText("/newbot") }} value="/newbot" />
        </li>
        <li>
          <span>{t("profile.private.telegram.stepOne.fill")}</span>
          <small>{t("profile.private.telegram.stepOne.usernameRule")}{" "}<CopyValueButton copied={copiedValue === suggestedUsername} label={t("profile.private.telegram.copy", { value: suggestedUsername })} onCopy={() => { void copyText(suggestedUsername) }} value={suggestedUsername} /></small>
        </li>
        <li><span>{t("profile.private.telegram.stepOne.success")}</span></li>
      </ol> : null}

      {setupStep === 2 ? <>
        <p className="profile-private-telegram__token-instruction">
          {t("profile.private.telegram.stepTwo.beforeBotFather")}{" "}<a href="https://t.me/BotFather" rel="noreferrer" target="_blank">@BotFather<ExternalLink aria-hidden="true" /></a>{" "}{t("profile.private.telegram.stepTwo.afterBotFather")}
        </p>
        <TextField
          disabled={busy}
          hint={t("profile.private.telegram.tokenHint")}
          label={t("profile.private.telegram.tokenLabel")}
          onChange={(value) => { setBotToken(value); setError(null) }}
          masked
          placeholder={t("profile.private.telegram.tokenPlaceholder")}
          value={botToken}
        />
      </> : null}

      {setupStep === 3 ? <>
        <dl className="profile-private-telegram__summary profile-private-telegram__summary--wizard">
          <IdentityRow
            displayName={currentAccount?.bot_display_name}
            fallback={t("profile.private.telegram.notAvailable")}
            label={t("profile.private.telegram.bot")}
            username={currentAccount?.bot_username}
          />
          <IdentityRow
            displayName={state === "active" ? currentAccount?.bound_display_name : t("profile.private.telegram.stepThree.ownerTarget")}
            fallback={t("profile.private.telegram.stepThree.ownerTarget")}
            label={t("profile.private.telegram.boundTo")}
            username={state === "active" ? currentAccount?.bound_telegram_username : null}
          />
        </dl>
        {state === "active" ? <div className="profile-private-telegram__success" role="status">
          <Check aria-hidden="true" />
          <strong>{t("profile.private.telegram.stepThree.successTitle")}</strong>
        </div> : <p className="profile-private-telegram__binding-instruction">
          {busyAction === "pairing" || !pairing
            ? t("profile.private.telegram.stepThree.preparing")
            : t("profile.private.telegram.stepThree.instruction")}
        </p>}
      </> : null}
    </section>

    {error ? <p className="profile-private-telegram__notice profile-private-telegram__notice--error" role="alert">{error}</p> : null}
    <div className="profile-private-telegram__wizard-actions">
      <Button disabled={busy} onClick={goBack} type="button" variant="ghost">
        {t("profile.private.telegram.previous")}
      </Button>
      {setupStep === 1 ? <Button onClick={() => setSetupStep(2)} type="button">
        {t("profile.private.telegram.stepOne.next")}
      </Button> : null}
      {setupStep === 2 ? <Button disabled={busy || botToken.trim().length < 10} onClick={() => { void configure() }} type="button">
        {busyAction === "configure" ? t("profile.private.telegram.configuring") : t("profile.private.telegram.stepTwo.next")}
      </Button> : null}
      {setupStep === 3 && state === "active" ? <Button onClick={() => closeSetup(false)} type="button">
        {t("profile.private.telegram.stepThree.done")}
      </Button> : null}
      {setupStep === 3 && state !== "active" && pairing ? <Button asChild>
        <a href={pairing.deep_link} rel="noreferrer" target="_blank">{t("profile.private.telegram.openTelegram")}<ExternalLink aria-hidden="true" /></a>
      </Button> : null}
      {setupStep === 3 && state !== "active" && !pairing ? <Button disabled={busyAction === "pairing"} onClick={() => { void createPairing() }} type="button">
        {busyAction === "pairing" || !error ? t("profile.private.telegram.creatingPairing") : t("profile.private.telegram.retry")}
      </Button> : null}
    </div>
  </ManageDialog>

  return <div className="profile-private-telegram">
    {accountError ? <p className="profile-private-telegram__notice profile-private-telegram__notice--error" role="alert">{accountError}</p> : null}
    <div className={`profile-private-telegram__card profile-private-telegram__card--${state}`}>
      <div className="profile-private-telegram__card-heading">
        <h4>Telegram</h4>
        <span className="profile-private-telegram__status">{t(`profile.private.telegram.states.${state}`)}</span>
      </div>
      {state === "active" ? <>
        <dl className="profile-private-telegram__summary">
          <IdentityRow
            displayName={currentAccount?.bot_display_name}
            fallback={t("profile.private.telegram.notAvailable")}
            label={t("profile.private.telegram.bot")}
            username={currentAccount?.bot_username}
          />
          <IdentityRow
            displayName={currentAccount?.bound_display_name}
            fallback={t("profile.private.telegram.notAvailable")}
            label={t("profile.private.telegram.boundTo")}
            username={currentAccount?.bound_telegram_username}
          />
        </dl>
        <div className="profile-private-telegram__actions">
          {botHref ? <Button asChild>
            <a href={botHref} rel="noreferrer" target="_blank">{t("profile.private.telegram.openTelegram")}<ExternalLink aria-hidden="true" /></a>
          </Button> : null}
          {editable ? <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button aria-label={t("profile.private.telegram.more")} disabled={busy} size="icon" type="button" variant="outline">
                <MoreHorizontal aria-hidden="true" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" className="profile-private-telegram__menu" sideOffset={6}>
                <DropdownMenu.Item className="profile-private-telegram__menu-item" onSelect={() => openSetup(2)}>{t("profile.private.telegram.card.reconfigure")}</DropdownMenu.Item>
                <DropdownMenu.Item className="profile-private-telegram__menu-item profile-private-telegram__menu-item--danger" onSelect={() => setConfirmDisconnect(true)}>{t("profile.private.telegram.disconnect")}</DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root> : null}
        </div>
      </> : <>
        <p className="profile-private-telegram__card-description">{state === "waiting_pairing" ? t("profile.private.telegram.card.waitingDescription") : state === "attention" ? (currentAccount?.issue ?? t("profile.private.telegram.attention")) : t("profile.private.telegram.card.unconfiguredDescription")}</p>
        {editable ? <Button onClick={() => openSetup()} type="button">
          {state === "waiting_pairing" ? t("profile.private.telegram.card.continue") : state === "attention" ? t("profile.private.telegram.card.reconfigure") : t("profile.private.telegram.card.start")}
        </Button> : <p className="profile-private-telegram__notice">{t("profile.private.telegram.ownerOnly")}</p>}
      </>}
    </div>
    {setupDialog}
    <ConfirmDialog
      confirmLabel={t("profile.private.telegram.disconnect")}
      danger
      description={t("profile.private.telegram.disconnectDescription")}
      onConfirm={() => { void disconnect() }}
      onOpenChange={setConfirmDisconnect}
      open={confirmDisconnect}
      pending={busyAction === "disconnect"}
      title={t("profile.private.telegram.disconnectTitle")}
    />
  </div>
}

function CopyValueButton({ copied, label, onCopy, value }: { readonly copied: boolean; readonly label: string; readonly onCopy: () => void; readonly value: string }) {
  return <button aria-label={label} className="profile-private-telegram__copy-value" onClick={onCopy} type="button">
    <code>{value}</code>
    {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
  </button>
}

function IdentityRow({ displayName, fallback, label, username }: { readonly displayName: string | null | undefined; readonly fallback: string; readonly label: string; readonly username: string | null | undefined }) {
  return <div>
    <dt>{label}</dt>
    <dd>
      <span>{displayName || (username ? `@${username}` : fallback)}</span>
      {displayName && username ? <small>@{username}</small> : null}
    </dd>
  </div>
}

function buildSuggestedUsername(elfieName: string, elfieId: string): string {
  const normalizedName = elfieName
    .toLowerCase()
    .replace(/_bot$/u, "")
    .replace(/[^a-z0-9]+/gu, "_")
    .replace(/^_+|_+$/gu, "")
  const fallbackId = elfieId.replace(/[^a-z0-9]/giu, "").slice(-6).padStart(6, "0")
  const base = normalizedName || `elfie_${fallbackId}`
  return `${base.slice(0, 28)}_bot`
}
