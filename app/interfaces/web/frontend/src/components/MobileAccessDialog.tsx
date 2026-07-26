import { useEffect, useState } from "react"
import QRCode from "qrcode"

import { ApiError, mobileAccess, type MobileAccess } from "../api/client"
import { Icon } from "./Icon"
import { SelectField } from "./SelectField"

type MobileAccessDialogProps = { readonly onClose: () => void; readonly targetPath?: "/chat" | "/manage" }

function accessError(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "手机访问地址读取失败"
}

function withTargetPath(url: string, targetPath: "/chat" | "/manage"): string {
  const target = new URL(url)
  target.pathname = targetPath
  return target.toString()
}

export function MobileAccessDialog({ onClose, targetPath = "/chat" }: MobileAccessDialogProps) {
  const [access, setAccess] = useState<MobileAccess | null>(null)
  const [selectedUrl, setSelectedUrl] = useState("")
  const [imageUrl, setImageUrl] = useState("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void mobileAccess()
      .then((result) => {
        if (cancelled) return
        const targetUrls = result.urls.map((url) => withTargetPath(url, targetPath))
        setAccess({ ...result, urls: targetUrls })
        setSelectedUrl(targetUrls[0] ?? "")
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(accessError(reason))
      })
    return () => { cancelled = true }
  }, [targetPath])

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
      if (!cancelled) setError("二维码生成失败")
    })
    return () => { cancelled = true }
  }, [selectedUrl])

  const unavailable = access !== null && !access.available
  return <section aria-labelledby="mobile-access-title" aria-modal="true" className="modal-backdrop" role="dialog">
    <article className="mobile-access-dialog">
      <button aria-label="关闭手机访问二维码" className="modal-close" onClick={onClose} type="button"><Icon name="x" /></button>
      <p className="brand">MOBILE ACCESS</p>
      <h2 id="mobile-access-title">用手机打开 ElfieNest</h2>
      {error ? <p className="notice notice--error">{error}</p> : null}
      {access === null && error === null ? <p>正在查找本机局域网地址…</p> : null}
      {unavailable ? <p className="mobile-access-dialog__hint">当前服务只允许本机访问。请以局域网模式启动后再扫码：<code>elfienest start --lan</code></p> : null}
      {access?.available && selectedUrl ? <>
        <img alt={`访问 ${selectedUrl} 的二维码`} className="mobile-access-dialog__qr" src={imageUrl} />
        {access.urls.length > 1 ? <label className="mobile-access-dialog__select">本机地址<SelectField ariaLabel="选择本机地址" onValueChange={setSelectedUrl} options={access.urls.map((url) => ({ label: url, value: url }))} value={selectedUrl} /></label> : null}
        <p className="mobile-access-dialog__url">{selectedUrl}</p>
        <p className="mobile-access-dialog__hint">手机和电脑接入同一个家庭网络后扫码。登录 Owner 账号进入管理台，普通账号进入聊天。</p>
      </> : null}
    </article>
  </section>
}
