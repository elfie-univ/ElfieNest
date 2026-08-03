import { useEffect, useMemo, useRef, useState } from "react"
import { Wordcloud } from "@visx/wordcloud"
import { useTranslation } from "react-i18next"

import type { RecentFocus } from "./model"

type ProfileRecentFocusProps = {
  readonly focus: RecentFocus
  readonly status: "ready" | "empty" | "unavailable"
}

type CloudTopic = {
  readonly text: string
  readonly value: number
}

type CloudSize = {
  readonly width: number
  readonly height: number
}

const FALLBACK_SIZE: CloudSize = { width: 640, height: 340 }

export function ProfileRecentFocus({ focus, status }: ProfileRecentFocusProps) {
  const { t } = useTranslation("chat")
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<CloudSize>(FALLBACK_SIZE)
  const topics = useMemo<readonly CloudTopic[]>(
    () => focus.topics.map((topic) => ({ text: topic.label, value: topic.weight })),
    [focus.topics],
  )
  const topicByLabel = useMemo(
    () => new Map(focus.topics.map((topic) => [topic.label, topic] as const)),
    [focus.topics],
  )

  useEffect(() => {
    if (status !== "ready" || topics.length === 0) return
    const container = containerRef.current
    if (container === null) return
    const updateSize = (): void => {
      const width = Math.max(280, Math.floor(container.clientWidth || container.getBoundingClientRect().width || FALLBACK_SIZE.width))
      const height = Math.max(220, Math.floor(container.clientHeight || container.getBoundingClientRect().height || Math.min(FALLBACK_SIZE.height, Math.max(250, width * 0.55))))
      setSize((current) => current.width === width && current.height === height ? current : { width, height })
    }
    updateSize()
    const observer = new ResizeObserver(updateSize)
    observer.observe(container)
    return () => observer.disconnect()
  }, [status, topics.length])

  if (status !== "ready" || topics.length === 0) {
    return <p className="profile-private-module__empty">{t("profile.private.focus.empty")}</p>
  }

  return (
    <div
      ref={containerRef}
      className="profile-private-focus__cloud"
      role="img"
      aria-label={t("profile.private.focus.topics")}
      data-testid="recent-focus-wordcloud"
    >
      <svg className="profile-private-focus__svg" viewBox={`0 0 ${size.width} ${size.height}`} aria-hidden="true">
        <Wordcloud
          words={[...topics]}
          width={size.width}
          height={size.height}
          font="Georgia, serif"
          fontSize={(word) => topicFontSize(word.value, size.width)}
          fontWeight={800}
          padding={5}
          random={stableRandom}
          rotate={(word, index) => topicRotation(word.value, index)}
          spiral="archimedean"
        >
          {(layoutWords) => layoutWords.map((word, index) => {
            const topic = topicByLabel.get(word.text ?? "")
            if (topic === undefined) return null
            const x = word.x ?? size.width / 2
            const y = word.y ?? size.height / 2
            const rotation = word.rotate ?? 0
            return (
              <text
                key={`${topic.id}-${index}`}
                className={`profile-private-focus__topic profile-private-focus__topic--${topicCategory(topic.category)}`}
                data-testid="recent-focus-topic"
                data-rotation={rotation}
                fontSize={word.size ?? topicFontSize(topic.weight, size.width)}
                textAnchor="middle"
                transform={`translate(${x} ${y}) rotate(${rotation})`}
              >
                {topic.label}
              </text>
            )
          })}
        </Wordcloud>
      </svg>
    </div>
  )
}

function topicFontSize(weight: number, width: number): number {
  const normalized = Math.min(1, Math.max(0, weight))
  const minimum = width < 480 ? 14 : 18
  const maximum = width < 480 ? 42 : 62
  return Math.round(minimum + Math.pow(normalized, 1.2) * (maximum - minimum))
}

function topicRotation(weight: number, index: number): number {
  return weight < 0.58 && index % 7 === 0 ? 90 : 0
}

function topicCategory(category: string): "person" | "place" | "emotion" | "activity" {
  switch (category) {
    case "person":
      return "person"
    case "place":
      return "place"
    case "emotion":
      return "emotion"
    default:
      return "activity"
  }
}

function stableRandom(): number {
  return 0.37
}
