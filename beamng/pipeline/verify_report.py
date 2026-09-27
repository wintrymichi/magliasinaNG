"""Summary of the final verification against the whole dataset (validate_metrics.py <tag> full).

Reads work/validation_full/metrics_<tag>.json (one entry per view v<pano>_<dir>), aggregates
per panorama, per direction and along the route, and writes VERIFICA.md (Italian, copied into
the level by build_level) plus a chart of the agreement along the road.
"""
import json, os, sys
import numpy as np
from config import WORK, DATASET

NAMES_IT = {"sky": "cielo", "building": "edifici", "vegetation": "vegetazione", "road": "strada",
            "wall": "muri", "rail_fence": "guardrail/recinzioni", "terrain": "terreno", "pole_sign": "pali/cartelli"}


def main(tag, base_tag=None):
    vdir = os.path.join(WORK, "validation_full")
    m = json.load(open(os.path.join(vdir, f"metrics_{tag}.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    dist = {d["index"]: d["route_dist_m"] for d in D}
    year = {d["index"]: str(d["date"])[:4] for d in D}
    per_pano, per_dir = {}, {}
    for name, v in m["per_view"].items():
        i, dn = int(name[1:5]), name[6:]
        per_pano.setdefault(i, []).append(v["agreement"])
        per_dir.setdefault(dn, []).append(v["agreement"])
    idx = np.array(sorted(per_pano))
    s = np.array([dist[i] for i in idx]); a = np.array([np.mean(per_pano[i]) for i in idx])
    order = np.argsort(s); s, a, idx = s[order], a[order], idx[order]
    # 200 m stretches
    bins = np.arange(0, s.max() + 200, 200)
    stretch = [(b, b + 200, float(np.mean(a[(s >= b) & (s < b + 200)])), int(((s >= b) & (s < b + 200)).sum()))
               for b in bins if ((s >= b) & (s < b + 200)).any()]
    worst = sorted(zip(a, idx, s))[:10]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 3.2), dpi=120)
    ax.plot(s / 1000, a, color="#9aa7b8", lw=0.8, label="panoramica")
    k = 9
    sm = np.convolve(a, np.ones(k) / k, mode="same")
    ax.plot(s[k // 2:-k // 2] / 1000, sm[k // 2:-k // 2], color="#1f5fbf", lw=2, label="media mobile (9)")
    ax.axhline(m["mean_pixel_agreement"], color="#c0392b", ls="--", lw=1, label="media %.3f" % m["mean_pixel_agreement"])
    ax.set_xlabel("distanza lungo la strada (km)"); ax.set_ylabel("concordanza pixel")
    ax.set_ylim(0, 1); ax.grid(alpha=0.3); ax.legend(loc="lower left", fontsize=8, frameon=False)
    ax.set_title("Foto Street View vs. BeamNG nella stessa posa, per panoramica (4 direzioni)", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(vdir, "concordanza_percorso.png")); plt.close(fig)
    L = []
    L.append("# Verifica finale contro l'intero dataset\n")
    L.append(f"Per ciascuna delle {len(idx)} panoramiche (4 direzioni: {m['views']} viste) la camera del gioco è stata "
             "messa nella posa calibrata della foto, con la stessa direzione e lo stesso campo visivo (90°). Foto e schermata "
             "sono state segmentate con lo stesso modello (Mask2Former, Mapillary Vistas) e confrontate pixel per pixel. "
             "Veicoli e persone nelle foto sono esclusi.\n")
    L.append("## Risultato complessivo\n")
    L.append(f"- Concordanza media dei pixel: **{m['mean_pixel_agreement']:.3f}**")
    L.append("- Sovrapposizione (IoU) per classe: " + ", ".join(f"{NAMES_IT[g]} {v:.2f}" for g, v in m["iou_overall"].items()))
    L.append("- Per direzione: " + ", ".join(f"{d} {np.mean(v):.3f}" for d, v in sorted(per_dir.items())))
    if base_tag and os.path.exists(os.path.join(vdir, f"metrics_{base_tag}.json")):
        b = json.load(open(os.path.join(vdir, f"metrics_{base_tag}.json")))
        L.append("\n## Effetto dell'ultimo ciclo di correzione\n")
        L.append("La stessa verifica, ripetuta prima dell'ultimo ciclo di confronto e correzione, aveva dato "
                 "i valori della colonna \"Prima\". Quel ciclo ha misurato nelle foto l'altezza dei muri, "
                 "portato a piena risoluzione le texture dei muri lunghi e aggiunto gli arbusti mancanti.\n")
        L.append("| Misura | Prima | Dopo |")
        L.append("|---|---|---|")
        L.append(f"| Concordanza media | {b['mean_pixel_agreement']:.3f} | {m['mean_pixel_agreement']:.3f} |")
        for g, v in m["iou_overall"].items():
            L.append(f"| IoU {NAMES_IT[g]} | {b['iou_overall'].get(g, float('nan')):.3f} | {v:.3f} |")
    L.append("\n## Lungo il percorso (tratti di 200 m)\n")
    L.append("| Tratto (m) | Panoramiche | Concordanza |")
    L.append("|---|---|---|")
    for b0, b1, v, n in stretch:
        L.append(f"| {b0:.0f}–{b1:.0f} | {n} | {v:.3f} |")
    L.append("\n## Le 10 panoramiche meno concordanti\n")
    L.append("| Panoramica | Distanza (m) | Anno | Concordanza |")
    L.append("|---|---|---|---|")
    for v, i, sv in worst:
        L.append(f"| {i:04d} | {sv:.0f} | {year[i]} | {v:.3f} |")
    L.append("\n## Come leggere i numeri\n")
    L.append("- Anche con due immagini identiche la concordanza non arriverebbe a 1: la segmentazione di foto e gioco "
             "ha il suo rumore. Cielo, strada e vegetazione pesano di più perché occupano più pixel.")
    L.append("- Pali e cartelli sono oggetti sottili: a 10 m, 0,3 m di errore valgono circa 25 pixel, più della loro "
             "larghezza. La loro IoU resta quindi bassa anche quando sono al posto giusto; le posizioni sono state "
             "verificate a parte, per riproiezione nelle foto.")
    L.append("- Tra 1,28 e 1,36 km non esistono panoramiche, quindi il tratto non entra nel confronto.")
    L.append("- Le differenze che restano sono soprattutto nella vegetazione: forma e specie delle piante, siepi e "
             "arbusti dei giardini privati, scarpate con reti paramassi. Il cielo è coperto nelle foto e a nubi sparse "
             "nel gioco.")
    open(os.path.join(vdir, "VERIFICA.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:8]))
    print("worst:", [(f"{i:04d}", round(float(v), 3)) for v, i, _ in worst[:5]])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "full", sys.argv[2] if len(sys.argv) > 2 else None)
