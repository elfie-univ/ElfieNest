import { useEffect, useRef } from "react"

import { Button } from "@/components/ui/button"

type SetupWelcomeProps = {
  readonly action: string
  readonly disabled?: boolean
  readonly onContinue: () => void
  readonly title: string
}

const foxAssetUrl = new URL("../assets/elfienest-fox-transparent.png", import.meta.url).href
const logoAssetUrl = new URL("../../../../../../docs/public/assets/elfienest-logo-mark-transparent.png", import.meta.url).href
const houseViewBox = "0 0 270.93332 270.93332"
const houseFillPath = "M 137.76678 17.545699 L 20.361548 116.53862 L 29.676225 128.3441 L 46.463831 114.26383 L 46.463831 247.80658 L 229.61079 247.91458 L 229.71931 114.37235 L 245.96535 127.91054 L 254.73794 115.99705 L 213.47327 80.905139 L 213.6898 51.337435 L 192.67816 51.229431 L 192.67816 63.576481 L 137.76678 17.545699 z M 137.84378 37.262325 L 214.45306 101.49406 L 214.19261 231.39053 L 61.365247 231.12956 L 61.365247 100.97265 L 137.84378 37.262325 z"
const houseRoofDrawPath = "M 247.74802,119.80303 136.08694,27.333702 24.425861,122.12931 52.341131,98.285013"
const houseBodyDrawPath = "M 52.341131,98.285013 53.504266,237.27979 220.99589,236.69822 224.4853,100.02972 201.80414,80.837968"
const houseLeftWallPath = "M 46.463831 114.26383 L 61.365247 100.97265 L 61.365247 231.12956 L 46.463831 247.80658 Z"
const houseBottomWallPath = "M 46.463831 247.80658 L 229.61079 247.91458 L 214.19261 231.39053 L 61.365247 231.12956 Z"
const houseRightWallPath = "M 214.45306 101.49406 L 229.71931 114.37235 L 229.61079 247.91458 L 214.19261 231.39053 Z"
const houseChimneyPath = "M 192.67816 51.229431 L 213.6898 51.337435 L 213.47327 80.905139 L 192.67816 63.576481 Z"
const radarCenter = { x: 208.4, y: 37.4 }
const groundSignalCenter = { x: 137.8, y: 220.5 }
const welcomeTitleStart = 15.65
const welcomeTitleCharacterDelay = 0.035
const radarBodyPath = `M 197.26755 31.834749 L 196.58283 31.932418 L 196.09397 32.22594 L 195.80045 32.421277 L 195.40926 32.812984 L 194.9204 33.350419 L 194.5783 34.475415 L 194.52921 35.160128 L 194.5783 36.3337 L 194.62688 37.458179 L 194.72455 38.485506 L 195.01807 39.707654 L 195.55602 41.22384 L 196.09397 42.299744 L 196.68102 43.130701 L 197.26755 43.864506 L 197.90317 44.597795 L 198.58788 45.282507 L 199.32168 45.918127 L 200.2994 46.651933 L 201.17997 47.23846 L 202.35354 47.727836 L 203.9183 48.363456 L 205.09187 48.656978 L 206.07011 48.852315 L 207.29226 48.949984 L 208.46583 48.901408 L 209.68849 48.803223 L 210.91116 48.412032 L 211.8403 47.87408 L 212.23149 47.48289 L 212.52501 47.140792 L 212.81802 46.505172 L 212.86711 46.064889 L 212.86711 45.478361 L 212.67177 44.500126 L 212.32916 43.717745 L 211.93797 42.935364 L 211.49768 42.348319 L 211.00883 41.663607 L 210.66673 41.126172 L 209.98201 40.098844 L 209.34639 39.414648 L 208.85702 38.729936 L 208.71077 38.534082 L 209.34639 37.849369 L 210.07968 36.96932 L 210.12878 36.431368 L 210.03111 36.08927 L 209.88435 35.84484 L 209.73759 35.551318 L 209.34639 35.404557 L 208.90611 35.355465 L 208.51492 35.45365 L 207.97697 35.893416 L 207.53669 36.480461 L 207.39044 36.72489 L 207.09692 37.066988 L 206.21635 36.3337 L 205.77659 35.84484 L 204.99421 35.208704 L 204.21182 34.670752 L 203.52711 34.133317 L 202.74473 33.693034 L 201.96235 33.204175 L 201.08178 32.763892 L 200.39707 32.421277 L 199.56611 32.079179 L 198.73464 31.883842 L 198.09902 31.834749 L 197.26755 31.834749 z M 197.61481 32.993852 L 198.60545 33.169035 L 199.47981 33.402096 L 200.41257 33.810339 L 201.57839 34.334855 L 202.68634 35.034554 L 203.50231 35.617464 L 204.08522 35.966797 L 205.01798 36.608101 L 205.54249 37.191012 L 206.24219 37.832316 L 205.89234 38.24056 L 205.71716 38.415226 L 205.65928 38.881864 L 205.83395 39.173319 L 206.06701 39.523169 L 206.53365 39.814624 L 206.94137 39.814624 L 207.23283 39.814624 L 207.81574 39.347986 L 208.16559 39.872502 L 208.63223 40.280745 L 209.21514 41.096716 L 209.73965 41.738021 L 210.1479 42.379325 L 210.61402 43.253691 L 211.13853 44.244845 L 211.54678 44.944027 L 211.54678 45.469059 L 211.42999 46.051969 L 211.37159 46.401302 L 210.84708 46.751152 L 210.0895 47.042607 L 209.4482 47.042607 L 208.7485 46.926335 L 208.16559 46.809546 L 207.64107 46.63488 L 207.11656 46.459696 L 206.64992 46.226636 L 205.71716 45.70212 L 204.02682 44.710966 L 203.44391 44.302722 L 202.9194 43.894995 L 202.1613 43.312085 L 201.22854 42.496114 L 200.64563 42.029476 L 199.77127 41.038322 L 199.36354 40.513806 L 198.83851 39.872502 L 198.48918 39.347986 L 197.73108 38.24056 L 197.43963 37.716044 L 197.20657 37.133134 L 196.97351 36.433435 L 196.85672 36.083586 L 196.68205 35.55907 L 196.56526 35.150826 L 196.3906 34.567916 L 196.44899 33.985006 L 196.62366 33.693551 L 197.0319 33.11064 L 197.61481 32.993852 z`
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
          <svg className="setup-welcome__svg" viewBox={houseViewBox}>
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
                    d={houseRoofDrawPath}
                    data-testid="setup-welcome-house-roof-path"
                    fill="none"
                    pathLength="1"
                  />
                  <path className="setup-welcome__house-phase-block" d={houseLeftWallPath} fill="black" />
                  <path className="setup-welcome__house-phase-block" d={houseBottomWallPath} fill="black" />
                  <path className="setup-welcome__house-phase-block" d={houseRightWallPath} fill="black" />
                  <path
                    className="setup-welcome__house-path setup-welcome__house-body-path"
                    d={houseBodyDrawPath}
                    data-testid="setup-welcome-house-body-path"
                    fill="none"
                    pathLength="1"
                  />
                  <path
                    className="setup-welcome__house-chimney-block"
                    d={houseChimneyPath}
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
              d={houseFillPath}
              fillRule="nonzero"
              mask="url(#setup-welcome-house-reveal)"
            />
            <path
              className="setup-welcome__house-fill setup-welcome__house-final-fill"
              data-testid="setup-welcome-house-final-fill"
              d={houseFillPath}
              fillRule="nonzero"
            />

            <g className="setup-welcome__radar" data-testid="setup-welcome-radar">
              <path className="setup-welcome__radar-body-path" d={radarBodyPath} fillRule="evenodd" />
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
