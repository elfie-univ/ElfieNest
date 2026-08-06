import { useEffect, useRef } from "react"

import { Button } from "@/components/ui/button"
import houseSvgSource from "../assets/elfienest-house.svg?raw"

type SetupWelcomeProps = {
  readonly action: string
  readonly disabled?: boolean
  readonly onContinue: () => void
  readonly title: string
}

const foxAssetUrl = new URL("../assets/elfienest-fox-transparent.png", import.meta.url).href
const logoAssetUrl = new URL("../../../../../../docs/public/assets/elfienest-logo-mark-transparent.png", import.meta.url).href

type HouseAsset = {
  readonly bodyDrawPath: string
  readonly bottomWallPath: string
  readonly chimneyPath: string
  readonly fillPath: string
  readonly leftWallPath: string
  readonly radarPath: string
  readonly roofDrawPath: string
  readonly rightWallPath: string
  readonly viewBox: string
}

type Point = readonly [number, number]

const svgNumberPattern = /[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g

function parsePolygonSubpaths(pathData: string): Point[][] {
  return pathData
    .split(/z/i)
    .map((subpath) => [...subpath.matchAll(svgNumberPattern)].map((match) => Number(match[0])))
    .filter((numbers) => numbers.length >= 4 && numbers.length % 2 === 0)
    .map((numbers) => Array.from({ length: numbers.length / 2 }, (_, index) => [numbers[index * 2], numbers[index * 2 + 1]] as Point))
}

function formatPolyline(points: readonly Point[]): string {
  const first = pointAt(points, 0, "polyline")
  const rest = points.slice(1)
  return `M ${first[0]} ${first[1]}${rest.map(([x, y]) => ` L ${x} ${y}`).join("")}`
}

function formatPolygon(points: readonly Point[]): string {
  return `${formatPolyline(points)} Z`
}

function splitDrawPath(pathData: string): { bodyDrawPath: string; roofDrawPath: string } {
  const polylineData = pathData.split(/\s+v\s+/i)[0]
  if (polylineData === undefined) {
    throw new Error("The welcome house SVG has no draw order")
  }
  const numbers = [...polylineData.matchAll(svgNumberPattern)].map((match) => Number(match[0]))
  if (numbers.length !== 16) {
    throw new Error("The welcome house SVG has an unexpected draw order")
  }
  const points = Array.from({ length: numbers.length / 2 }, (_, index) => [numbers[index * 2], numbers[index * 2 + 1]] as Point)
  return {
    roofDrawPath: formatPolyline(points.slice(0, 4)),
    bodyDrawPath: formatPolyline(points.slice(3)),
  }
}

function pointAt(points: readonly Point[], index: number, label: string): Point {
  const point = points[index]
  if (point === undefined) {
    throw new Error(`The welcome house SVG has an incomplete ${label}`)
  }
  return point
}

function readPathData(document: Document, id: string): string {
  const element = document.getElementById(id)
  const path = element?.getAttribute("d")
  if (path === null || path === undefined || path.length === 0) {
    throw new Error(`The welcome house SVG is missing path data for ${id}`)
  }
  return path
}

function parseHouseAsset(source: string): HouseAsset {
  const parsed = new DOMParser().parseFromString(source, "image/svg+xml")
  const viewBox = parsed.documentElement.getAttribute("viewBox")
  if (viewBox === null || viewBox.length === 0) {
    throw new Error("The welcome house SVG is missing its viewBox")
  }
  const fillPath = readPathData(parsed, "path1")
  const drawSegments = splitDrawPath(readPathData(parsed, "path2"))
  const [outerWall, innerWall] = parsePolygonSubpaths(fillPath)
  if (outerWall === undefined || innerWall === undefined || outerWall.length < 13 || innerWall.length < 5) {
    throw new Error("The welcome house SVG has an unexpected fill geometry")
  }

  return {
    bodyDrawPath: drawSegments.bodyDrawPath,
    bottomWallPath: formatPolygon([pointAt(outerWall, 4, "bottom wall"), pointAt(outerWall, 5, "bottom wall"), pointAt(innerWall, 2, "bottom wall"), pointAt(innerWall, 3, "bottom wall")]),
    chimneyPath: formatPolygon([pointAt(outerWall, 11, "chimney"), pointAt(outerWall, 10, "chimney"), pointAt(outerWall, 9, "chimney"), pointAt(outerWall, 12, "chimney")]),
    fillPath,
    leftWallPath: formatPolygon([pointAt(outerWall, 3, "left wall"), pointAt(innerWall, 4, "left wall"), pointAt(innerWall, 3, "left wall"), pointAt(outerWall, 4, "left wall")]),
    radarPath: readPathData(parsed, "path3"),
    roofDrawPath: drawSegments.roofDrawPath,
    rightWallPath: formatPolygon([pointAt(innerWall, 1, "right wall"), pointAt(outerWall, 6, "right wall"), pointAt(outerWall, 5, "right wall"), pointAt(innerWall, 2, "right wall")]),
    viewBox,
  }
}

const houseAsset = parseHouseAsset(houseSvgSource)
const radarCenter = { x: 208.4, y: 37.4 }
const groundSignalCenter = { x: 137.8, y: 220.5 }
const welcomeTitleStart = 16.1
const welcomeTitleCharacterDelay = 0.035
const houseInteriorPath = "M 137.84378 37.262325 L 214.45306 101.49406 L 214.19261 231.39053 L 61.365247 231.12956 L 61.365247 100.97265 Z"

export function SetupWelcome({ action, disabled = false, onContinue, title }: SetupWelcomeProps) {
  const copyReadyRef = useRef(false)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      copyReadyRef.current = true
    }, welcomeTitleStart * 1000)
    return () => window.clearTimeout(timer)
  }, [])

  const titleDelay = (index: number): number => copyReadyRef.current
    ? index * welcomeTitleCharacterDelay
    : welcomeTitleStart + index * welcomeTitleCharacterDelay
  const actionDelay = copyReadyRef.current
    ? title.length * welcomeTitleCharacterDelay + 0.55
    : welcomeTitleStart + title.length * welcomeTitleCharacterDelay + 0.55

  return (
    <section aria-labelledby="setup-welcome-title" className="setup-welcome">
      <div aria-hidden="true" className="setup-welcome__art" data-testid="setup-welcome-art">
        <div className="setup-welcome__stage">
          <svg className="setup-welcome__svg" data-house-source="elfienest-house.svg" viewBox={houseAsset.viewBox}>
            <defs>
              <filter id="setup-welcome-beam-glow" x="-80%" y="-20%" width="260%" height="140%">
                <feGaussianBlur stdDeviation="3.2" />
              </filter>
              <clipPath id="setup-welcome-house-interior">
                <path d={houseInteriorPath} />
              </clipPath>
              <mask id="setup-welcome-house-reveal" height="270.93332" maskContentUnits="userSpaceOnUse" maskUnits="userSpaceOnUse" style={{ maskType: "luminance" }} width="270.93332" x="0" y="0">
                <rect fill="black" height="270.93332" width="270.93332" x="0" y="0" />
                <g className="setup-welcome__house-drawing" data-testid="setup-welcome-house-drawing">
                  <path
                    className="setup-welcome__house-path setup-welcome__house-roof-path"
                    d={houseAsset.roofDrawPath}
                    data-testid="setup-welcome-house-roof-path"
                    fill="none"
                    pathLength="1"
                  />
                  <path className="setup-welcome__house-phase-block" d={houseAsset.leftWallPath} fill="black" />
                  <path className="setup-welcome__house-phase-block" d={houseAsset.bottomWallPath} fill="black" />
                  <path className="setup-welcome__house-phase-block" d={houseAsset.rightWallPath} fill="black" />
                  <path
                    className="setup-welcome__house-path setup-welcome__house-body-path"
                    d={houseAsset.bodyDrawPath}
                    data-testid="setup-welcome-house-body-path"
                    fill="none"
                    pathLength="1"
                  />
                  <path
                    className="setup-welcome__house-chimney-block"
                    d={houseAsset.chimneyPath}
                    data-testid="setup-welcome-house-chimney-block"
                    fill="black"
                  />
                  <rect
                    className="setup-welcome__house-chimney-wipe"
                    data-testid="setup-welcome-house-chimney-wipe"
                    fill="white"
                    height="31.5"
                    width="22.5"
                    x="192"
                    y="50.5"
                  />
                </g>
              </mask>
            </defs>

            <path
              className="setup-welcome__house-fill"
              data-testid="setup-welcome-house-fill"
              d={houseAsset.fillPath}
              fillRule="nonzero"
              mask="url(#setup-welcome-house-reveal)"
            />
            <path
              className="setup-welcome__house-fill setup-welcome__house-final-fill"
              data-testid="setup-welcome-house-final-fill"
              d={houseAsset.fillPath}
              fillRule="nonzero"
            />

            <g className="setup-welcome__radar" data-testid="setup-welcome-radar">
              <path className="setup-welcome__radar-body-path" d={houseAsset.radarPath} fillRule="evenodd" />
              <circle className="setup-welcome__radar-dot" cx={radarCenter.x} cy={radarCenter.y} r="2.1" />
            </g>

            <g className="setup-welcome__radar-rings" data-testid="setup-welcome-radar-rings">
              <circle cx={radarCenter.x} cy={radarCenter.y} r="5.4" />
            </g>

            <g className="setup-welcome__signal" data-testid="setup-welcome-signal">
              <circle cx={radarCenter.x} cy={radarCenter.y} r="8.1" />
              <circle cx={radarCenter.x} cy={radarCenter.y} r="8.1" />
              <circle cx={radarCenter.x} cy={radarCenter.y} r="8.1" />
            </g>

            <g className="setup-welcome__ground-ripples" clipPath="url(#setup-welcome-house-interior)" data-testid="setup-welcome-ground-ripples">
              <ellipse cx={groundSignalCenter.x} cy={groundSignalCenter.y} rx="5.8" ry="2.4" />
              <ellipse cx={groundSignalCenter.x} cy={groundSignalCenter.y} rx="5.8" ry="2.4" />
              <ellipse cx={groundSignalCenter.x} cy={groundSignalCenter.y} rx="5.8" ry="2.4" />
            </g>

            <g className="setup-welcome__beam" data-testid="setup-welcome-beam">
              <path className="setup-welcome__beam-glow" d={`M208.4 44.2C199 91 169 171 ${groundSignalCenter.x} ${groundSignalCenter.y}`} pathLength="1" />
              <path className="setup-welcome__beam-line" d={`M208.4 44.2C199 91 169 171 ${groundSignalCenter.x} ${groundSignalCenter.y}`} pathLength="1" />
              <circle className="setup-welcome__beam-dot" cx={groundSignalCenter.x} cy={groundSignalCenter.y} r="2.9" />
            </g>
          </svg>

          <div className="setup-welcome__fox-window">
            <div className="setup-welcome__fox-figure">
              <img alt="" className="setup-welcome__fox" draggable="false" src={foxAssetUrl} data-testid="setup-welcome-fox" />
              <span aria-hidden="true" className="setup-welcome__fox-eye-glint" data-testid="setup-welcome-fox-eye-glint" />
            </div>
          </div>
          <img
            alt=""
            className="setup-welcome__final-logo"
            data-testid="setup-welcome-final-logo"
            draggable="false"
            src={logoAssetUrl}
          />
        </div>
      </div>
      <div className="setup-welcome__copy">
        <h1 aria-label={title} className="setup-welcome__title" id="setup-welcome-title">
          {Array.from(title).map((character, index) => (
            <span aria-hidden="true" className="setup-welcome__title-char" key={`${character}-${index}`} style={{ animationDelay: `${titleDelay(index)}s` }}>
              {character === " " ? "\u00a0" : character}
            </span>
          ))}
        </h1>
        <Button
          className="setup-welcome__action"
          disabled={disabled}
          onClick={onContinue}
          size="lg"
          style={{ animationDelay: `${actionDelay}s` }}
          type="button"
        >
          {action}
        </Button>
      </div>
    </section>
  )
}
