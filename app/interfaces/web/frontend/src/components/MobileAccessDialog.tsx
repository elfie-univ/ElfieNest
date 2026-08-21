import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import QRCode from "qrcode"

import { Button } from "@/components/ui/button"
import { mobileAccess, type MobileAccess } from "../api/admin/runtime"
import { localizeApiError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Icon } from "./Icon"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"

type MobileAccessDialogProps = { readonly onClose: () => void; readonly targetPath?: "/chat" | "/manage" | "/monitor" }
type MobileAccessError =
  | { readonly kind: "api"; readonly reason: unknown }
  | { readonly kind: "qr" }
type WifiLookupStatus =
  | "idle"
  | "checking"
  | "available"
  | "permission_denied"
  | "location_services_disabled"
  | "permission_unknown"
  | "ssid_unavailable"
  | "helper_unavailable"
  | "helper_timeout"
  | "unsupported"

function withTargetPath(url: string, targetPath: "/chat" | "/manage" | "/monitor"): string {
  const target = new URL(url)
  target.pathname = targetPath
  return target.toString()
}

export function MobileAccessDialog({ onClose, targetPath = "/chat" }: MobileAccessDialogProps) {
  const { i18n, t } = useTranslation("common")
  const [access, setAccess] = useState<MobileAccess | null>(null)
  const [selectedUrl, setSelectedUrl] = useState("")
  const [imageUrl, setImageUrl] = useState("")
  const [error, setError] = useState<MobileAccessError | null>(null)
  const [wifiLookupStatus, setWifiLookupStatus] = useState<WifiLookupStatus>("idle")

  useEffect(() => {
    let cancelled = false
    void mobileAccess()
      .then(async (result) => {
        if (cancelled) return
        const targetUrls = result.urls.map((url) => withTargetPath(url, targetPath))
        setAccess({ ...result, urls: targetUrls })
        setSelectedUrl(targetUrls[0] ?? "")
        if (result.network_name !== null) {
          setWifiLookupStatus("available")
          return
        }

        const desktop = window.elfienestDesktop
        if (desktop === undefined) {
          setWifiLookupStatus("unsupported")
          return
        }
        setWifiLookupStatus("checking")
        try {
          const nativeResult = await desktop.readCurrentWifiName()
          if (cancelled) return
          setWifiLookupStatus(nativeResult.status)
          if (nativeResult.status === "available" && nativeResult.network_name !== null) {
            setAccess((current) => current === null ? current : { ...current, network_name: nativeResult.network_name })
          }
        } catch {
          if (!cancelled) setWifiLookupStatus("helper_unavailable")
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError({ kind: "api", reason })
      })
    return () => { cancelled = true }
  }, [targetPath])

  const openLocationSettings = (): void => {
    void window.elfienestDesktop?.openLocationSettings()
  }

  useEffect(() => {
    let cancelled = false
    if (!selectedUrl) {
      setImageUrl("")
      return () => { cancelled = true }
    }
    void QRCode.toDataURL(selectedUrl, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 280,
      color: { dark: "#183d2d", light: "#fffdf5" },
    }).then((value) => {
      if (!cancelled) setImageUrl(value)
    }).catch(() => {
      if (!cancelled) setError({ kind: "qr" })
    })
    return () => { cancelled = true }
  }, [selectedUrl])

  const unavailable = access !== null && !access.available
  return <section aria-label={t("mobileAccess.title")} aria-modal="true" className="modal-backdrop" role="dialog">
    <article className="mobile-access-dialog">
      <Button aria-label={t("mobileAccess.close")} className="modal-close" onClick={onClose} size="icon" type="button" variant="ghost"><Icon name="x" /></Button>
      <p className="brand">{t("mobileAccess.brand")}</p>
      {access !== null ? <>
        <h2 className="mobile-access-dialog__step">{t(access.network_name ? "mobileAccess.connectWifi" : "mobileAccess.connectSameWifi")}</h2>
        {access.network_name ? <p className="mobile-access-dialog__network">{access.network_name}</p> : null}
      </> : null}
      {error ? <Notice kind="error" message={error.kind === "qr" ? t("mobileAccess.qrError") : localizeApiError(error.reason, "manage.load", currentLocale(i18n))} /> : null}
      {access === null && error === null ? <p>{t("mobileAccess.loading")}</p> : null}
      {wifiLookupStatus === "checking" ? <p className="mobile-access-dialog__hint">{t("mobileAccess.wifiPermissionRequesting")}</p> : null}
      {wifiLookupStatus === "permission_denied" || wifiLookupStatus === "location_services_disabled" ? <div className="mobile-access-dialog__permission">
        <Notice kind="warning" message={t("mobileAccess.wifiPermissionDenied")} />
        <Button onClick={openLocationSettings} size="sm" type="button" variant="link">{t("mobileAccess.openLocationSettings")}</Button>
      </div> : null}
      {wifiLookupStatus === "ssid_unavailable" || wifiLookupStatus === "permission_unknown" || wifiLookupStatus === "helper_timeout" || wifiLookupStatus === "helper_unavailable" ? <p className="mobile-access-dialog__hint">{t("mobileAccess.wifiNameUnavailable")}</p> : null}
      {unavailable ? <p className="mobile-access-dialog__hint">{t("mobileAccess.unavailable")}</p> : null}
      {access?.available && selectedUrl ? <>
        <h2 className="mobile-access-dialog__step mobile-access-dialog__step--scan">{t("mobileAccess.scanQr")}</h2>
        <img alt={t("mobileAccess.qrAlt", { url: selectedUrl })} className="mobile-access-dialog__qr" src={imageUrl} />
        {access.urls.length > 1 ? <div className="mobile-access-dialog__select"><SelectField label={t("mobileAccess.localAddress")} onValueChange={setSelectedUrl} options={access.urls.map((url) => ({ label: url, value: url }))} value={selectedUrl} /></div> : null}
        <p className="mobile-access-dialog__url">{selectedUrl}</p>
      </> : null}
    </article>
  </section>
}
