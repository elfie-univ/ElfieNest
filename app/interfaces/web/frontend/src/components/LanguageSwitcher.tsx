import { useTranslation } from "react-i18next"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { setLocale, type SupportedLocale } from "@/i18n/locale"

import { Icon } from "./Icon"
import { SelectField } from "./SelectField"

const languageOptions = [
  { label: "简体中文", value: "zh-CN" },
  { label: "English", value: "en-US" },
] as const

const unavailableStorage = {
  getItem: () => null,
  removeItem: () => undefined,
  setItem: () => undefined,
} as const

type LanguageSwitcherProps = {
  readonly disabled?: boolean
  readonly variant?: "field" | "compact"
}

function parseSupportedLocale(value: string | undefined): SupportedLocale | null {
  if (value === "zh-CN" || value === "en-US") return value
  return null
}

function getSafeStorage(): Pick<Storage, "getItem" | "removeItem" | "setItem"> {
  try {
    return window.localStorage
  } catch (error) {
    if (error instanceof DOMException || error instanceof Error) {
      return unavailableStorage
    }
    throw error
  }
}

export function LanguageSwitcher({ disabled = false, variant = "field" }: LanguageSwitcherProps) {
  const { i18n: instance, t } = useTranslation("common")
  const currentLocale =
    parseSupportedLocale(instance.resolvedLanguage) ??
    parseSupportedLocale(instance.language) ??
    "zh-CN"

  const selectLocale = (value: string): void => {
    const locale = parseSupportedLocale(value) ?? "zh-CN"
    setLocale(instance, locale, {
      storage: getSafeStorage(),
      browserLanguages: [],
      documentElement: document.documentElement,
    })
  }

  if (variant === "compact") {
    return <div className="w-full min-w-0 max-w-full" data-language-switcher>
      <Select disabled={disabled} onValueChange={selectLocale} value={currentLocale}>
        <SelectTrigger aria-label={t("language.label")} className="setup-locale-control__trigger">
          <Icon name="globe-2" size={16} />
          <SelectValue>{languageOptions.find((option) => option.value === currentLocale)?.label}</SelectValue>
        </SelectTrigger>
        <SelectContent position="popper">
          {languageOptions.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  }

  return (
    <div className="w-full min-w-0 max-w-full" data-language-switcher>
      <SelectField
        disabled={disabled}
        label={t("language.label")}
        onValueChange={selectLocale}
        options={languageOptions}
        value={currentLocale}
      />
    </div>
  )
}
