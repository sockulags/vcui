import { Download, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { inTauri } from "../voice/engine"

type UpdateState =
  | { kind: "none" }
  | { kind: "available"; version: string; install: () => Promise<void> }
  | { kind: "installing"; version: string; percent: number | null }
  | { kind: "failed"; message: string }

/**
 * Looks for a new release when the app starts and offers to install it.
 * Releases are signed in CI; the updater checks the signature against the
 * public key in tauri.conf.json before it installs anything.
 */
export function UpdateBanner() {
  const [state, setState] = useState<UpdateState>({ kind: "none" })

  useEffect(() => {
    if (!inTauri() || import.meta.env.DEV) return
    let cancelled = false
    void (async () => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater")
        const update = await check()
        if (!update || cancelled) return
        setState({
          kind: "available",
          version: update.version,
          install: async () => {
            const { invoke } = await import("@tauri-apps/api/core")
            const { relaunch } = await import("@tauri-apps/plugin-process")
            let total = 0
            let done = 0
            setState({ kind: "installing", version: update.version, percent: null })
            try {
              // The installer replaces the engine's files, so stop it first.
              await invoke("stop_engine")
              await update.downloadAndInstall((event) => {
                if (event.event === "Started") total = event.data.contentLength ?? 0
                if (event.event === "Progress") {
                  done += event.data.chunkLength
                  setState({ kind: "installing", version: update.version, percent: total ? Math.round((done / total) * 100) : null })
                }
              })
              await relaunch()
            } catch (error) {
              setState({ kind: "failed", message: error instanceof Error ? error.message : String(error) })
            }
          },
        })
      } catch (error) {
        console.warn("Update check failed", error)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (state.kind === "none") return null
  if (state.kind === "failed") return <div className="update-pill" data-failed>Uppdateringen misslyckades: {state.message}</div>
  if (state.kind === "installing") {
    return (
      <div className="update-pill">
        <RefreshCw size={14} className="spin" aria-hidden="true" />
        Installerar {state.version}
        {state.percent !== null ? ` · ${state.percent} %` : "…"}
      </div>
    )
  }
  return (
    <button type="button" className="update-pill" onClick={() => void state.install()}>
      <Download size={14} aria-hidden="true" />
      Version {state.version} finns – uppdatera
    </button>
  )
}
