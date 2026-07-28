import { cloneElement, useId, type ReactElement } from "react"

import "./manage-controls.css"

type FieldControlProps = {
  readonly "aria-describedby"?: string | undefined
  readonly "aria-invalid"?: true | undefined
  readonly "aria-labelledby"?: string | undefined
  readonly id?: string | undefined
}

type FieldControlRenderProps = {
  readonly describedBy?: string | undefined
  readonly inputId: string
  readonly invalid?: true | undefined
  readonly labelId: string
}

type FieldRowProps = {
  readonly control: ReactElement<FieldControlProps> | ((props: FieldControlRenderProps) => ReactElement)
  readonly decorateControl?: boolean
  readonly error?: string | undefined
  readonly hint?: string | undefined
  readonly inputId: string
  readonly label: string
}

export function FieldRow({ control, decorateControl = true, error, hint, inputId, label }: FieldRowProps) {
  const fallbackId = useId()
  const labelId = `${inputId || fallbackId}-label`
  const hintId = hint ? `${inputId || fallbackId}-hint` : undefined
  const errorId = error ? `${inputId || fallbackId}-error` : undefined
  const fallbackDescribedBy = typeof control === "function" ? undefined : control.props["aria-describedby"]
  const describedBy = errorId ?? hintId ?? fallbackDescribedBy
  const renderedControl = typeof control === "function"
    ? control({ describedBy, inputId, invalid: error ? true : undefined, labelId })
    : decorateControl
      ? cloneElement(control, {
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : control.props["aria-invalid"],
        "aria-labelledby": control.props["aria-labelledby"] ?? labelId,
        id: control.props.id ?? inputId,
      })
      : control

  return <div aria-labelledby={labelId} className="manage-field" data-field-row="true" role="group">
    <div className="manage-field__label-column">
      <label className="manage-field__label" htmlFor={inputId} id={labelId}>{label}</label>
      {hint ? <small className="manage-field__hint" id={hintId}>{hint}</small> : null}
    </div>
    <div className="manage-field__control-column">
      {renderedControl}
      {error ? <small className="manage-field__error" id={errorId}>{error}</small> : null}
    </div>
  </div>
}
