#!/usr/bin/env python3
"""seatcheck: will a seat hold the person sitting on it, and will it tip?

Reads a seating model (GLB, STL, or a folder of STLs; one mesh per part, assembled in place),
builds a voxel finite-element model with each part's own material (wood is orthotropic along its
grain, metal is isotropic), loads it the way people load seats (sitting, dropping in, perching on
an edge, leaning, optionally standing), and reports:

  strength  every part against its material, with a safety factor, plus axial crush and buckling
  joints    every place two parts touch (glued, dry, bolted, screwed) and every bolted cut through
            a one-piece body, from the forces the FE model passes through that joint
  fatigue   metal parts under the everyday sit, cycled
  tipping   rigid-body overturning about every edge of the footprint: edge test, perching on the very
            edge, leaning, push-to-tip force, and how far to move feet / seat / add weight to fix it
  stiffness how far the seat sinks under a person

Output: a pass / warn / fail table with margins (margin = capacity / demand after the required
safety factor; 1.00 is the line), the fixes, a JSON file and a one-page PNG sheet.

  python3 seatcheck.py MODEL.glb --spec piece.seatcheck.json [--res 0.125] [--out DIR]

Units follow the spec ("units": "in" | "mm" | "cm" | "m", "up": "z" | "y"). Everything internal
is SI. Needs: pip install trimesh numpy scipy pyamg shapely rtree pillow
"""
import argparse, json, math, os, re, sys, time, hashlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
G = 9.81
UNITS = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "inch": 0.0254, "ft": 0.3048}

DRY = ("dry", "rest", "loose")

DEFAULTS = {
    "occupant_kg": 113,          # 250 lb design occupant
    "dynamic_factor": 2.0,       # dropping onto the seat
    "edge_factor": 1.5,          # sitting down hard on an edge or end
    "lean_frac": 0.15,           # horizontal push at seat height while leaning / rocking, x occupant weight
    "stand": False,              # also check someone standing on it (1.5 x weight on a 100 mm pad)
    "pad_d_mm": 200,             # sitting load pad diameter
    "edge_pad_d_mm": 120,        # local pad for edge / end loads
    "edge_in_mm": 60,            # edge loads centred this far in from the seat edge
    "tip_edge_N": 600,           # edge stability test vertical load
    "tip_edge_push_N": 20,       # edge stability test outward push at seat height
    "perch_must_hold": True,     # full weight perched on the edge must not tip it
    "perch_in_mm": 50,           # where a perching sitter's weight lands, in from the seat edge
    "sf": {"crush_perp": 1.25, "wood": 2.5, "metal": 1.5, "fatigue": 1.5, "glue": 2.5, "bolt": 2.0, "screw": 1.0},
    "warn_margin": 1.2,
    "floor": "friction",         # or "slippery"
    "mu_floor": 0.3,
    "deflection_warn_mm": 5.0,
    "floor_tol_mm": 2.0,         # what it rests on: bottom points within this of the lowest
    "rock_tol_mm": 15.0,         # what it settles onto if it rocks: bottom points within this
    "rock_warn_mm": 5.0,
    "rock_max_deg": 6.0,         # only bottom points it can rock onto within this tilt (not rounded toes)         # warn if the seat top moves more than this while it rocks onto them
}

# ----------------------------------------------------------------------------------------------
# model and spec


def load_parts(path, units, up):
    import trimesh
    s = UNITS[units]
    parts = {}
    if os.path.isdir(path):
        for f in sorted(os.listdir(path)):
            if f.lower().endswith((".stl", ".obj", ".ply")):
                parts[os.path.splitext(f)[0]] = trimesh.load(os.path.join(path, f), force="mesh")
    else:
        sc = trimesh.load(path)
        if isinstance(sc, trimesh.Trimesh):
            parts[os.path.splitext(os.path.basename(path))[0]] = sc
        else:
            for node in sc.graph.nodes_geometry:
                T, gname = sc.graph[node]
                m = sc.geometry[gname].copy(); m.apply_transform(T)
                name = node if node not in parts else f"{node}_{len(parts)}"
                parts[name] = m
    out = {}
    for k, m in parts.items():
        m = m.copy(); v = np.asarray(m.vertices, float) * s
        if up == "y":
            v = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
        m.vertices = v
        out[k] = m
    return out


def load_materials():
    return json.load(open(os.path.join(HERE, "materials.json")))


def find_material(name, lib):
    n = name.strip().lower()
    for kind in ("wood", "metal"):
        for k, v in lib[kind].items():
            if k.startswith("_"):
                continue
            if n == k.lower() or n in [a.lower() for a in v.get("aka", [])]:
                d = dict(v); d["name"] = k; d["kind"] = kind
                return d
    raise SystemExit(f"unknown material '{name}'. Add it to materials.json or use one of: "
                     + ", ".join(k for kd in ("wood", "metal") for k in lib[kd] if not k.startswith("_")))


def part_config(name, spec):
    cfg = {}
    for rx, c in spec.get("parts", {}).items():
        if re.search(rx, name):
            cfg = dict(c); break
    role = cfg.get("role")
    if role is None:
        role = "pad" if re.search(r"(?i)cushion|pad|upholster|leather|foam|strap|piping", name) else "structure"
    if re.search(r"(?i)^deco_", name):
        role = "ignore"
    cfg["role"] = role
    return cfg


# ----------------------------------------------------------------------------------------------
# voxels


def voxelize(mesh, origin, h, shape):
    """Occupancy of cell centres by winding number along +z, one ray per column."""
    nx, ny, nz = shape
    b = mesh.bounds
    i0 = max(0, int(math.floor((b[0, 0] - origin[0]) / h)) - 1); i1 = min(nx, int(math.ceil((b[1, 0] - origin[0]) / h)) + 1)
    j0 = max(0, int(math.floor((b[0, 1] - origin[1]) / h)) - 1); j1 = min(ny, int(math.ceil((b[1, 1] - origin[1]) / h)) + 1)
    occ = np.zeros(shape, bool)
    if i1 <= i0 or j1 <= j0:
        return occ
    I, J = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), indexing="ij")
    I = I.ravel(); J = J.ravel()
    jit = h * 1e-4 * np.array([0.6180339, 0.4142136])
    org = np.column_stack([origin[0] + (I + 0.5) * h + jit[0], origin[1] + (J + 0.5) * h + jit[1],
                           np.full(len(I), b[0, 2] - h)])
    dirs = np.tile([0.0, 0.0, 1.0], (len(I), 1))
    try:
        from trimesh.ray.ray_pyembree import RayMeshIntersector
        rmi = RayMeshIntersector(mesh)
    except Exception:
        rmi = mesh.ray
    locs, ridx, tri = rmi.intersects_location(org, dirs, multiple_hits=True)
    if len(ridx) == 0:
        return occ
    # signed crossings (winding number along the ray), so overlapping or self-intersecting shells
    # (unioned-by-touching strands, a mesh that isn't booleaned) still fill correctly
    sg = -np.sign(mesh.face_normals[tri, 2])
    order = np.lexsort((locs[:, 2], ridx))
    ridx = ridx[order]; zz = locs[order, 2]; sg = sg[order]
    zc = origin[2] + (np.arange(nz) + 0.5) * h
    starts = np.r_[0, np.flatnonzero(np.diff(ridx)) + 1]; ends = np.r_[starts[1:], len(ridx)]
    for s0, e0 in zip(starts, ends):
        z = zz[s0:e0]; g = sg[s0:e0]
        if len(z) > 1:            # a ray through a shared edge hits both faces: count it once
            keep = np.r_[True, (np.diff(z) > h * 1e-6) | (g[1:] != g[:-1])]; z = z[keep]; g = g[keep]
        w = np.cumsum(g)
        r = ridx[s0]
        col = np.zeros(nz, bool)
        for k in range(len(z) - 1):
            if w[k] != 0:
                col |= (zc >= z[k]) & (zc < z[k + 1])
        occ[I[r], J[r], :] |= col
    return occ


# ----------------------------------------------------------------------------------------------
# finite elements (8-node bricks on a regular grid)

GP = np.array([-1, 1]) / math.sqrt(3)
LOC = np.array([[a & 1, (a >> 1) & 1, (a >> 2) & 1] for a in range(8)])   # local node offsets


def bmat(xi, h):
    s = 2 * LOC - 1
    dN = np.zeros((8, 3))
    for a in range(8):
        f = [(1 + s[a, k] * xi[k]) for k in range(3)]
        dN[a, 0] = s[a, 0] * f[1] * f[2] / 8; dN[a, 1] = f[0] * s[a, 1] * f[2] / 8; dN[a, 2] = f[0] * f[1] * s[a, 2] / 8
    dN *= 2.0 / h
    B = np.zeros((6, 24))
    for a in range(8):
        x, y, z = dN[a]
        B[:, 3 * a] = [x, 0, 0, 0, z, y]
        B[:, 3 * a + 1] = [0, y, 0, z, 0, x]
        B[:, 3 * a + 2] = [0, 0, z, y, x, 0]
    return B


def gmat(xi, h):
    """Strains of Wilson's 9 incompatible bubble modes (1 - xi_k^2) per displacement component."""
    G = np.zeros((6, 9))
    for m in range(3):
        g = np.zeros(3); g[m] = -2 * xi[m] * 2.0 / h
        x, y, z = g
        G[:, 3 * m] = [x, 0, 0, 0, z, y]
        G[:, 3 * m + 1] = [0, y, 0, z, 0, x]
        G[:, 3 * m + 2] = [0, 0, z, y, x, 0]
    return G


def element_K(D, h):
    """Incompatible-mode brick (Wilson / Taylor H11): bends correctly with 2 cells through a board,
    where a plain 8-node brick locks and comes out several times too stiff. Returns K and the
    strain-recovery matrices at the 8 corners."""
    Kcc = np.zeros((24, 24)); Kci = np.zeros((24, 9)); Kii = np.zeros((9, 9)); dv = (h / 2) ** 3
    for a in GP:
        for b in GP:
            for c in GP:
                B = bmat((a, b, c), h); Gm = gmat((a, b, c), h)
                Kcc += B.T @ D @ B * dv; Kci += B.T @ D @ Gm * dv; Kii += Gm.T @ D @ Gm * dv
    Ki = np.linalg.inv(Kii)
    K = Kcc - Kci @ Ki @ Kci.T
    # strain at each corner: B u + G alpha, alpha = -Kii^-1 Kci^T u; evaluate at the Gauss points
    # nearest each corner, extrapolated linearly to the corner
    E = np.zeros((8, 6, 24))
    for n in range(8):
        xi = (2 * LOC[n] - 1).astype(float)
        E[n] = bmat(xi, h) - gmat(xi, h) @ Ki @ Kci.T
    return K, E


SHEAR_IDX = {(1, 2): 3, (0, 2): 4, (0, 1): 5}


def D_matrix(mat, grain, ratios):
    E = mat["E"] * 1e6
    if mat["kind"] == "metal" or mat.get("isotropic") or grain in (None, "none"):
        nu = 0.3 if mat["kind"] == "metal" else 0.3
        lam = E * nu / ((1 + nu) * (1 - 2 * nu)); mu = E / (2 * (1 + nu))
        D = np.zeros((6, 6)); D[:3, :3] = lam; D[np.arange(3), np.arange(3)] += 2 * mu; D[3:, 3:] = np.eye(3) * mu
        return D
    a = "xyz".index(grain); p, q = [k for k in range(3) if k != a]
    EL = E; ET = E * ratios["E_perp_over_EL"]; GLT = E * ratios["G_par_over_EL"]; GTT = E * ratios["G_roll_over_EL"]
    nLT = ratios["nu_par"]; nTT = ratios["nu_perp"]
    S = np.zeros((6, 6))
    S[a, a] = 1 / EL; S[p, p] = S[q, q] = 1 / ET
    S[a, p] = S[p, a] = S[a, q] = S[q, a] = -nLT / EL
    S[p, q] = S[q, p] = -nTT / ET
    for pair, idx in SHEAR_IDX.items():
        S[idx, idx] = 1 / (GTT if set(pair) == {p, q} else GLT)
    return np.linalg.inv(S)


def rigid_modes(X):
    n = len(X); B = np.zeros((3 * n, 6))
    B[0::3, 0] = 1; B[1::3, 1] = 1; B[2::3, 2] = 1
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    B[0::3, 3] = -y; B[1::3, 3] = x
    B[1::3, 4] = -z; B[2::3, 4] = y
    B[0::3, 5] = z; B[2::3, 5] = -x
    return B


class FEModel:
    def __init__(self, owner, origin, h, parts, mats, dry_pairs=()):
        """dry_pairs: part-index pairs that only bear on each other (no tension, no glue). Every other
        touching pair is bonded. Dry pairs get their own nodes, joined by contact springs that let go
        in tension (solved by an active-set loop)."""
        import scipy.sparse as sp
        from scipy.sparse.csgraph import connected_components
        self.owner = owner; self.origin = np.asarray(origin, float); self.h = h
        self.parts = parts; self.mats = mats
        nx, ny, nz = owner.shape; self.shape = owner.shape
        ijk = np.argwhere(owner >= 0); self.ijk = ijk; self.ne = ne = len(ijk)
        self.epart = owner[ijk[:, 0], ijk[:, 1], ijk[:, 2]]
        self.eid = -np.ones(owner.shape, np.int64); self.eid[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = np.arange(ne)
        Ng = (nx + 1) * (ny + 1) * (nz + 1)
        gn = lambda i, j, k: i + (nx + 1) * (j + (ny + 1) * k)
        en = np.stack([gn(ijk[:, 0] + LOC[a, 0], ijk[:, 1] + LOC[a, 1], ijk[:, 2] + LOC[a, 2]) for a in range(8)], 1)
        key = self.epart[:, None].astype(np.int64) * Ng + en
        uk, inv = np.unique(key.ravel(), return_inverse=True)
        self.faces = part_interfaces(self)
        dry = {tuple(sorted(p)) for p in dry_pairs}
        ea_, eb_ = [], []
        for pA in range(len(parts)):
            pass
        gper = {}
        for pi in range(len(parts)):
            gper[pi] = np.unique(en[self.epart == pi])
        for (pA, pB) in self.faces:
            if (pA, pB) in dry:
                continue
            com = np.intersect1d(gper[pA], gper[pB])
            ea_.append(np.searchsorted(uk, pA * Ng + com)); eb_.append(np.searchsorted(uk, pB * Ng + com))
        # parts that touch only along an edge or corner are bonded too (no face pair) -- leave them apart
        if ea_:
            a_ = np.concatenate(ea_); b_ = np.concatenate(eb_)
            gr = sp.coo_matrix((np.ones(len(a_)), (a_, b_)), shape=(len(uk), len(uk)))
            _, lab = connected_components(gr, directed=False)
        else:
            lab = np.arange(len(uk))
        _, lab = np.unique(lab, return_inverse=True)
        self.enode = lab[inv].reshape(ne, 8); self.nn = int(lab.max()) + 1
        gid = np.zeros(self.nn, np.int64); gid[lab] = uk % Ng
        k = gid // ((nx + 1) * (ny + 1)); r = gid % ((nx + 1) * (ny + 1)); j = r // (nx + 1); i = r % (nx + 1)
        self.nijk = np.column_stack([i, j, k]); self.X = self.origin + self.nijk * h
        # contact springs for dry pairs: node pairs across each shared face
        sa, sb, sd, sg, sk, sp_ = [], [], [], [], [], []
        for (pA, pB), fl in self.faces.items():
            if (pA, pB) not in dry:
                continue
            Eref = min(mats[pA]["mat"]["E"] * (1 if mats[pA]["mat"]["kind"] == "metal" else 0.075),
                       mats[pB]["mat"]["E"] * (1 if mats[pB]["mat"]["kind"] == "metal" else 0.075)) * 1e6
            for dd in range(3):
                q = fl[:, 0] == dd
                if not q.any(): continue
                ea, eb, sg_ = fl[q, 1], fl[q, 2], fl[q, 3]
                # A's face nodes: on the side facing B
                for la in np.flatnonzero(LOC[:, dd] == 0):
                    lb_hi = la + (1 << dd)              # same corner, other side
                    # if B is above A (sgn +1): A uses its hi corner, B its lo corner
                    nA = np.where(sg_ > 0, self.enode[ea, lb_hi], self.enode[ea, la])
                    nB = np.where(sg_ > 0, self.enode[eb, la], self.enode[eb, lb_hi])
                    sa.append(nA); sb.append(nB); sd.append(np.full(len(nA), dd)); sg.append(sg_)
                    sk.append(np.full(len(nA), Eref * h / 4)); sp_.append(np.full(len(nA), (pA << 16) + pB))
        if sa:
            sa = np.concatenate(sa); sb = np.concatenate(sb); sd = np.concatenate(sd); sg = np.concatenate(sg)
            sk = np.concatenate(sk); spp = np.concatenate(sp_)
            kk = np.stack([sa, sb, sd, sg], 1)
            uq, iv = np.unique(kk, axis=0, return_inverse=True)
            self.spr = dict(a=uq[:, 0], b=uq[:, 1], d=uq[:, 2], s=uq[:, 3], k=np.bincount(iv.ravel(), weights=sk),
                            pair=np.bincount(iv.ravel(), weights=spp) / np.bincount(iv.ravel()))
            self.spr["pair"] = self.spr["pair"].astype(np.int64)
            self.active = np.ones(len(uq), bool)
        else:
            self.spr = None; self.active = None
        self.edof = (3 * self.enode[:, :, None] + np.arange(3)).reshape(ne, 24)
        # one stiffness per (material, grain) group
        self.groups = {}; self.egroup = np.zeros(ne, np.int64)
        keys = {}
        for pi in range(len(parts)):
            m = mats[pi]
            if m is None:
                continue
            key = (m["mat"]["name"], m["grain"])
            if key not in keys:
                D = m["D"]; keys[key] = len(keys)
                K_, E_ = element_K(D, h)
                self.groups[keys[key]] = dict(D=D, K=K_, E=E_)
            self.egroup[self.epart == pi] = keys[key]
        rows, cols, vals = [], [], []
        for g, d in self.groups.items():
            sel = np.flatnonzero(self.egroup == g)
            ed = self.edof[sel]
            rows.append(np.repeat(ed, 24, axis=1).ravel()); cols.append(np.tile(ed, (1, 24)).ravel())
            vals.append(np.broadcast_to(d["K"].ravel(), (len(sel), 576)).ravel())
        N = 3 * self.nn
        self.K = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(N, N))
        del rows, cols, vals
        # self weight
        self.fg = np.zeros(N)
        rho = np.array([mats[p]["mat"]["density"] if mats[p] else 0 for p in range(len(parts))])
        w = rho[self.epart] * G * h ** 3 / 8
        np.add.at(self.fg, 3 * self.enode.ravel() + 2, -np.repeat(w, 8))

    def spring_K(self):
        import scipy.sparse as sp
        N = 3 * self.nn
        if self.spr is None or not self.active.any():
            return sp.csr_matrix((N, N))
        s = self.spr; m = self.active
        a, b, k = s["a"][m], s["b"][m], s["k"][m]
        r, c, v = [], [], []
        for comp in range(3):
            da, db = 3 * a + comp, 3 * b + comp
            r += [da, db, da, db]; c += [da, db, db, da]; v += [k, k, -k, -k]
        return sp.csr_matrix((np.concatenate(v), (np.concatenate(r), np.concatenate(c))), shape=(N, N))

    def supports(self, floor, mu=None):
        self._cache = getattr(self, "_cache", {})
        ck = (floor, None if self.active is None else hashlib.md5(self.active.tobytes()).hexdigest())
        self._ck = ck
        if ck in self._cache:
            self.fixed, self.free, self.Kff, self._ml = self._cache[ck]; self.floor = floor
            return
        self._base = getattr(self, "_base", {})
        if floor in self._base:
            self.fixed, self.free, Kel, self.floor_nodes, self._pre = self._base[floor]
            Ks = self.spring_K()
            self.Kff = (Kel + Ks[self.free][:, self.free]).tocsr()
            self._ml = None; self.floor = floor
            for k_ in [k_ for k_ in self._cache if k_[0] == floor and k_[1] is not None]:
                del self._cache[k_]                  # keep only the newest contact set per floor
            self._cache[ck] = (self.fixed, self.free, self.Kff, None)
            return
        self._pre = None
        bot = self.nijk[:, 2] == 0
        ids = np.flatnonzero(bot)
        fixed = [3 * ids + 2]
        if floor == "slippery":
            c = self.X[ids, :2].mean(0); d = np.linalg.norm(self.X[ids, :2] - c, axis=1)
            a = ids[np.argmin(d)]; far = ids[np.argmax(d)]
            fixed += [np.array([3 * a, 3 * a + 1, 3 * far + (0 if abs(self.X[far, 1] - self.X[a, 1]) > abs(self.X[far, 0] - self.X[a, 0]) else 1)])]
        else:
            fixed += [3 * ids, 3 * ids + 1]
        self.fixed = np.unique(np.concatenate(fixed)); self.floor_nodes = ids
        free = np.ones(3 * self.nn, bool); free[self.fixed] = False; self.free = np.flatnonzero(free)
        Kel = self.K[self.free][:, self.free].tocsr()
        self.Kff = (Kel + self.spring_K()[self.free][:, self.free]).tocsr()
        self._ml = None; self.floor = floor
        self._base[floor] = [self.fixed, self.free, Kel, ids, None]
        self._cache[ck] = (self.fixed, self.free, self.Kff, None)

    def solve(self, f):
        """Solve, letting dry contacts that pull apart go (and re-closing ones that press), up to 8 rounds."""
        if self.spr is None:
            return self._solve(f)
        floor = self.floor; tot = 0
        self._last_active = getattr(self, "_last_active", {})
        if floor in self._last_active:
            self.active = self._last_active[floor].copy()      # start from the last case's contact
        else:
            self.active[:] = True
        u = None
        NR = 5; nxt = None
        for it in range(NR):
            self.supports(floor)
            t_ = time.time(); u, n_ = self._solve(f, u); tot += n_
            if os.environ.get("SEATCHECK_DEBUG"):
                import resource
                rss = open("/proc/self/status").read().split("VmRSS:")[1].split()[0]
                print(f"    contact round {it}: {n_} it, {time.time()-t_:.1f}s, active {int(self.active.sum())}/{len(self.active)}, rss {int(rss)//1024} MB", flush=True)
            s = self.spr
            gap = s["s"] * (u[3 * s["b"] + s["d"]] - u[3 * s["a"] + s["d"]])
            new = gap <= 1e-9
            self.lifted = set()
            for pr in np.unique(s["pair"]):
                q = s["pair"] == pr
                if not new[q].any():           # would come apart completely: keep the 4 closest so it stays solvable
                    idx = np.flatnonzero(q)[np.argsort(gap[q])[:4]]
                    new[idx] = True; self.lifted.add(int(pr))
            # springs that were open but now overlap must close again
            changed = int((new != self.active).sum())
            nxt = new
            if changed == 0 or (it >= 1 and changed <= max(4, 0.005 * len(new))) or it == NR - 1:
                break
            self.active = new
        self.contact_rounds = it + 1
        self.contact_unsettled = int((nxt != self.active).sum()) if nxt is not None else 0
        self._last_active[floor] = (nxt if nxt is not None else self.active).copy()
        return u, tot

    def spring_forces(self, u):
        """Force on the A-side node of each active spring, (n,3)."""
        s = self.spr; m = self.active
        F = np.zeros((len(s["a"]), 3))
        for comp in range(3):
            F[:, comp] = s["k"] * (u[3 * s["b"] + comp] - u[3 * s["a"] + comp])
        F[~m] = 0
        return F

    def _solve(self, f, u0=None):
        try:
            import pypardiso
        except ImportError:
            pypardiso = None
        if pypardiso is not None and len(self.free) <= int(os.environ.get("SEATCHECK_DIRECT_MAX_DOF", 650000)):
            # direct sparse solve (multithreaded); one factorization in memory at a time, reused while
            # the stiffness (floor and contact set) stays the same
            if not hasattr(self, "_ps"):
                self._ps = pypardiso.PyPardisoSolver()
            if getattr(self, "_pkey", None) != self._ck:
                try: self._ps.free_memory(everything=False)
                except Exception: pass
                self._ps.factorize(self.Kff); self._pK = self.Kff; self._pkey = self._ck
            x = self._ps.solve(self._pK, f[self.free])
            u = np.zeros(3 * self.nn); u[self.free] = x
            return u, 1
        import pyamg, scipy.sparse.linalg as spla
        b = f[self.free]
        x0 = None if u0 is None else u0[self.free]
        if self._ml is None and getattr(self, "_pre", None) is not None:
            # contact set changed a little: reuse the first round's multigrid as a preconditioner
            res = []
            x, info = spla.cg(self.Kff, b, x0=x0, rtol=1e-9, maxiter=600, M=self._pre.aspreconditioner(cycle="V"),
                              callback=lambda xk: res.append(1))
            if info == 0:
                u = np.zeros(3 * self.nn); u[self.free] = x
                return u, len(res)
        if self._ml is None:
            Bm = rigid_modes(self.X)[self.free]
            self._ml = pyamg.smoothed_aggregation_solver(self.Kff, B=Bm, max_coarse=2000)
            self._cache[self._ck] = (self.fixed, self.free, self.Kff, self._ml)
            if self.floor in getattr(self, "_base", {}) and self._base[self.floor][4] is None:
                self._base[self.floor][4] = self._ml
        res = []
        x = self._ml.solve(b, x0=x0, tol=1e-9, accel="cg", maxiter=800, residuals=res)
        rel = res[-1] / max(res[0], 1e-30) if res else 0
        if rel > 1e-5:   # keep iterating first: a direct solve of ~600k dof needs >11 GB and was OOM-killed (23 Nov 2026)
            res2 = []
            x = self._ml.solve(b, x0=x, tol=1e-9, accel="cg", maxiter=4000, residuals=res2)
            rel = res2[-1] / max(res[0], 1e-30) if res2 else rel
            res += res2
        if rel > 1e-5:
            print(f"  warning: solver residual {rel:.1e}, falling back to direct solve", flush=True)
            x = spla.spsolve(self.Kff.tocsc(), b)
        u = np.zeros(3 * self.nn); u[self.free] = x
        return u, len(res)

    def stresses(self, u):
        """Corner stresses (ne, 8, 6) and element nodal forces (ne, 24)."""
        S = np.zeros((self.ne, 8, 6)); Fint = np.zeros((self.ne, 24))
        for g, d in self.groups.items():
            sel = np.flatnonzero(self.egroup == g)
            ue = u[self.edof[sel]]
            eps = np.einsum("nij,ej->eni", d["E"], ue)
            S[sel] = eps @ d["D"].T
            Fint[sel] = ue @ d["K"].T
        return S, Fint


def smooth_field(model, S):
    """Average corner stresses at each node over the elements of the same part (nodal recovery).
    Returns (ne, 8, 6): each element's corners carry the part's averaged nodal stress."""
    key = model.epart[:, None] * model.nn + model.enode
    k = key.ravel(); uk, inv = np.unique(k, return_inverse=True)
    cnt = np.bincount(inv)
    out = np.zeros((len(uk), 6))
    for c in range(6):
        out[:, c] = np.bincount(inv, weights=S[:, :, c].ravel()) / cnt
    return out[inv].reshape(S.shape)


def _old_smooth_field(model, S):
    from scipy.ndimage import uniform_filter
    out = np.zeros_like(S)
    i, j, k = model.ijk.T
    for p in np.unique(model.epart):
        sel = model.epart == p
        lo = model.ijk[sel].min(0); hi = model.ijk[sel].max(0) + 1
        shp = tuple(hi - lo)
        m = np.zeros(shp); m[tuple((model.ijk[sel] - lo).T)] = 1
        cnt = uniform_filter(m, 3, mode="constant")
        for c in range(6):
            a = np.zeros(shp); a[tuple((model.ijk[sel] - lo).T)] = S[sel, c]
            out[sel, c] = (uniform_filter(a, 3, mode="constant") / np.maximum(cnt, 1e-9))[tuple((model.ijk[sel] - lo).T)]
    return out


def von_mises(S):
    sx, sy, sz, tyz, txz, txy = S.T
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (tyz ** 2 + txz ** 2 + txy ** 2))


def principal_max(S):
    T = np.zeros((len(S), 3, 3))
    T[:, 0, 0], T[:, 1, 1], T[:, 2, 2] = S[:, 0], S[:, 1], S[:, 2]
    T[:, 1, 2] = T[:, 2, 1] = S[:, 3]; T[:, 0, 2] = T[:, 2, 0] = S[:, 4]; T[:, 0, 1] = T[:, 1, 0] = S[:, 5]
    return np.linalg.eigvalsh(T)[:, -1]


def wood_util(S, grain, mat, crush_ratio=1.0):
    """Utilization (stress / strength, no safety factor) and the governing mode, per element."""
    a = "xyz".index(grain); p, q = [k for k in range(3) if k != a]
    sL = S[:, a]; sp_, sq = S[:, p], S[:, q]
    shear_pq = S[:, SHEAR_IDX[(min(p, q), max(p, q))]]
    lt = [SHEAR_IDX[tuple(sorted((a, p)))], SHEAR_IDX[tuple(sorted((a, q)))]]
    tLT = np.sqrt(S[:, lt[0]] ** 2 + S[:, lt[1]] ** 2)
    MOR, fcp, fv, ftp = mat["MOR"] * 1e6, mat["fc_perp"] * 1e6, mat["fv"] * 1e6, mat["ft_perp"] * 1e6
    # tension across the grain: the larger principal stress in the cross-grain plane
    c = (sp_ + sq) / 2; r = np.sqrt(((sp_ - sq) / 2) ** 2 + shear_pq ** 2)
    sT_max, sT_min = c + r, c - r
    modes = np.column_stack([np.abs(sL) / MOR, np.maximum(sT_max, 0) / ftp, np.maximum(-sT_min, 0) / fcp * crush_ratio,
                             tLT / fv, np.abs(shear_pq) / (0.25 * fv)])
    names = np.array(["bending / along the grain", "tension across the grain (splitting)", "crushing across the grain",
                      "shear along the grain", "rolling shear"])
    k = np.argmax(modes, 1)
    return modes[np.arange(len(S)), k], names[k]


# ----------------------------------------------------------------------------------------------
# seat geometry and loads


def seat_footprint(meshes, top_band):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []; ztop = max(m.bounds[1, 2] for m in meshes)
    for m in meshes:
        n = m.face_normals; c = m.triangles_center
        sel = (n[:, 2] > 0.2) & (c[:, 2] > ztop - top_band)
        for t in m.triangles[sel]:
            p = Polygon(t[:, :2])
            if p.area > 0:
                polys.append(p.buffer(1e-6))
    fp = unary_union(polys).buffer(0)
    return fp, ztop


def load_columns(model, pad_owner, seat_struct_ids, patch, total, seat_is_pad):
    """Return dict node -> force vector for a patch load (shapely geometry in xy) of total force vector."""
    import shapely
    nx, ny, nz = model.shape; h = model.h; o = model.origin
    cx = o[0] + (np.arange(nx) + 0.5) * h; cy = o[1] + (np.arange(ny) + 0.5) * h
    CX, CY = np.meshgrid(cx, cy, indexing="ij")
    inpatch = shapely.contains_xy(patch, CX, CY)
    own = model.owner
    if seat_is_pad:
        # structural cells with a pad cell directly above
        # structural top faces with the pad directly above, or across a voxel gap of up to 2 cells
        padn = pad_owner >= 0
        near = np.zeros_like(padn)
        for g in (1, 2, 3):
            near[:, :, :-g] |= padn[:, :, g:]
        top = own >= 0
        top[:, :, :-1] &= own[:, :, 1:] < 0
        above = top & near
    else:
        above = np.isin(own, list(seat_struct_ids))
        above[:, :, :-1] &= own[:, :, 1:] < 0      # top faces only
    has = above.any(2)
    ktop = np.where(has, nz - 1 - np.argmax(above[:, :, ::-1], 2), -1)
    cols = np.argwhere(inpatch)
    if len(cols) == 0:
        raise SystemExit("load patch misses the seat")
    sup = np.argwhere(has)
    if len(sup) == 0:
        raise SystemExit("nothing under the seat carries load (check the seat / pad roles)")
    under = has[cols[:, 0], cols[:, 1]]
    if under.sum() >= 4:
        # the sitter's load spreads evenly over whatever carries the seat under the pad
        # (an overhanging cushion strip doesn't pile its share onto the nearest edge)
        tgt = cols[under]
    else:
        from scipy.spatial import cKDTree
        tree = cKDTree(sup)
        _, nearest = tree.query(cols)
        tgt = sup[nearest]
    w = np.full(len(tgt), 1.0 / len(tgt))
    F = {}
    for (i, j), wi in zip(tgt, w):
        k = ktop[i, j]
        e = model.eid[i, j, k]
        for a in (4, 5, 6, 7):      # top face nodes
            n = model.enode[e, a]
            F[n] = F.get(n, 0) + np.asarray(total) * wi / 4
    return F


# ----------------------------------------------------------------------------------------------
# joints


def part_interfaces(model):
    own = model.owner; faces = {}
    for d in range(3):
        sl_a = [slice(None)] * 3; sl_b = [slice(None)] * 3
        sl_a[d] = slice(0, -1); sl_b[d] = slice(1, None)
        a = own[tuple(sl_a)]; b = own[tuple(sl_b)]
        m = (a >= 0) & (b >= 0) & (a != b)
        idx = np.argwhere(m)
        if len(idx) == 0:
            continue
        ia = idx.copy(); ib = idx.copy(); ib[:, d] += 1
        pa = own[tuple(ia.T)]; pb = own[tuple(ib.T)]
        for pA, pB, ea, eb in zip(pa, pb, model.eid[tuple(ia.T)], model.eid[tuple(ib.T)]):
            key = (min(pA, pB), max(pA, pB)); sgn = 1
            if pA > pB:
                ea, eb = eb, ea; sgn = -1
            faces.setdefault(key, []).append((d, ea, eb, sgn))
    return {k: np.array(v) for k, v in faces.items()}


def resultant(model, Fint, elemsA, shared_nodes):
    """Force and moment (about the shared-node centroid) that the rest of the body puts on element set A."""
    en = model.enode[elemsA]; f = Fint[elemsA].reshape(len(elemsA), 8, 3)
    m = np.isin(en, shared_nodes)
    F = f[m].sum(0)
    X = model.X[en[m]]
    c = model.X[shared_nodes].mean(0)
    M = np.cross(X - c, f[m]).sum(0)
    return F, M, c


def plane_basis(P):
    c = P.mean(0); w, v = np.linalg.eigh(np.cov((P - c).T) + 1e-18 * np.eye(3))
    return c, v[:, 0], v[:, 2], v[:, 1]     # centroid, normal, major, minor


def bolt_group(F, M, c, n_ab, pos, pry=None):
    """Elastic bolt-group forces. pos: (k,3) bolt positions. Returns per-bolt tension and shear (N).
    Bolts in one line (a flange bolted to a post) can't resist a moment about that line by their spread:
    the plate pries about its edge instead, so that moment goes to tension over the pry lever `pry` (m,
    bolt line to the plate edge it tips on; default 2.5 bolt diameters if not given). Without this, a
    nearly-straight line gave a near-singular inertia and absurd tension (1.3 MN on an M6, 23 Nov 2026),
    and an exactly straight line gave none at all."""
    k = len(pos); cb = pos.mean(0)
    Mb = M + np.cross(c - cb, F)
    r = pos - cb; r -= np.outer(r @ n_ab, n_ab)
    Nt = F @ n_ab; V = F - Nt * n_ab
    Mn = Mb @ n_ab; Mbend = Mb - Mn * n_ab
    T_pry = 0.0
    if k >= 2:
        sv = np.linalg.svd(r, compute_uv=False)
        if sv[1] < 0.05 * sv[0]:                    # one line of bolts
            e1 = np.linalg.svd(r)[2][0]
            r = np.outer(r @ e1, e1)
            m1 = Mbend @ e1                         # moment about the bolt line: prying
            T_pry = abs(m1) / (k * (pry or 0.015))
            Mbend = Mbend - m1 * e1
    I = r.T @ r
    kv = np.linalg.pinv(I) @ np.cross(n_ab, Mbend)
    T = Nt / k + r @ kv + T_pry
    rr = np.linalg.norm(r, axis=1); J = (rr ** 2).sum()
    Vt = np.abs(Mn) * rr / J if J > 0 else 0 * rr
    Vb = np.linalg.norm(V) / k + Vt
    return T, Vb


def auto_bolts(P, n, major, minor, count, d):
    c = P.mean(0); a = (P - c) @ major; b = (P - c) @ minor
    ea = max(a.max() - 1.5 * d, 0.0); eb = max(b.max() - 1.5 * d, 0.0)
    if count == 1:
        pts = [c]
    elif count == 2:
        pts = [c + ea * major, c - ea * major]
    elif count == 3:
        pts = [c + ea * major, c - ea * major, c + eb * minor]
    else:
        pts = [c + sa * ea * major + sb * eb * minor for sa in (1, -1) for sb in (1, -1)]
        for q in range(count - 4):
            pts.append(c + ((q % 2) * 2 - 1) * ea * 0.0 * major)
    fits = (a.max() - a.min()) >= (3 * d if count >= 2 else 2 * d) and (b.max() - b.min()) >= 3 * d
    return np.array(pts), bool(fits)


# ----------------------------------------------------------------------------------------------
# tipping (rigid body)


def settled_footprint(bot, max_deg, ndir=72):
    """What the piece stands on once it has rocked, if its feet aren't flat. A bottom point counts if
    the piece reaches it by tilting at most max_deg about the edge of the strip it rests on (so not
    rounded toes or the underside of a rail). Returns the outline of those points and, per outward
    direction n, the effective tilt toward n it took to land there (rad): loads shift out by z sin(that)."""
    import shapely, shapely.ops
    from shapely.geometry import MultiPoint
    rest = bot[:, 2] < 2e-3
    rh = MultiPoint(bot[rest, :2]).convex_hull
    P = shapely.points(bot[:, :2])
    dist = shapely.distance(rh, P)
    ok = rest | ((dist > 1e-4) & (bot[:, 2] <= math.tan(math.radians(max_deg)) * dist))
    poly = MultiPoint(bot[ok, :2]).convex_hull
    dirs = []
    idx = np.flatnonzero(ok)
    for k in range(ndir):
        a = 2 * math.pi * k / ndir; n = np.array([math.cos(a), math.sin(a)])
        s_ = bot[idx, :2] @ n
        j = idx[np.argmax(s_)]
        if rest[j] or dist[j] <= 1e-4:
            dirs.append((n, float(s_.max()), 0.0)); continue
        q = np.array(shapely.ops.nearest_points(rh, P[j])[0].coords[0])
        m = (bot[j, :2] - q) / dist[j]
        th = math.atan(bot[j, 2] / dist[j])
        dirs.append((n, float(s_.max()), math.asin(max(0.0, math.sin(th) * float(m @ n)))))
    return poly, dirs


def tipping(hull, com_xy, mass_kg, fp, seat_top, cfg, units_s, com_z=None, bottom=None):
    W = cfg["occupant_kg"] * G; Wp = mass_kg * G
    com_z = seat_top / 2 if com_z is None else com_z
    e = cfg["edge_in_mm"] / 1000
    pts = np.array(hull.exterior.coords)[:-1]
    ccw = hull.exterior.is_ccw
    fpts = []
    geoms = getattr(fp, "geoms", [fp])
    for g in geoms:
        fpts.append(np.array(g.exterior.coords))
    fpts = np.vstack(fpts)
    seat_c = np.array(fp.centroid.coords[0])
    rows = []
    for i in range(len(pts)):
        p0, p1 = pts[i], pts[(i + 1) % len(pts)]
        t = p1 - p0; L = np.linalg.norm(t)
        if L < 1e-6:
            continue
        t /= L
        n = np.array([t[1], -t[0]]) if ccw else np.array([-t[1], t[0]])
        c = n @ p0
        th = max((t_ for n_, c_, t_ in bottom if n_ @ n > math.cos(math.radians(360 / len(bottom)))), default=0.0) if bottom else 0.0
        sn = math.sin(th)
        d = lambda q, z=seat_top: n @ q - c + z * sn       # tilted onto this edge first, if it rocks
        far = fpts[np.argmax(fpts @ n)]
        loads_edge = [(cfg["tip_edge_N"], d(far - e * n)), (Wp, d(com_xy, com_z))]
        loads_perch = [(W, d(far - cfg["perch_in_mm"] / 1000 * n)), (Wp, d(com_xy, com_z))]
        loads_lean = [(W, d(seat_c)), (Wp, d(com_xy, com_z))]
        H_lean = cfg["lean_frac"] * W
        def margin(loads, H, shift=0.0, seat_in=0.0, ballast=0.0):
            R = O = 0.0
            for k, (F, dd) in enumerate(loads):
                dd = dd - shift - (seat_in if k == 0 else 0.0)
                if dd < 0: R += F * -dd
                else: O += F * dd
            R += ballast * G * (-(d(np.array(hull.centroid.coords[0])) - shift))
            O += H * seat_top
            return R / O if O > 1e-12 else float("inf")
        R_c = sum(F * max(-dd, 0) for F, dd in loads_lean)
        O_c = sum(F * max(dd, 0) for F, dd in loads_lean)
        H_tip = max(R_c - O_c, 0) / seat_top
        cases = {
            "edge test": (margin(loads_edge, cfg["tip_edge_push_N"]), loads_edge, cfg["tip_edge_push_N"]),
            "perch on the edge": (margin(loads_perch, 0.0), loads_perch, 0.0),
            "lean": (margin(loads_lean, H_lean), loads_lean, H_lean),
        }
        for name, (mg, loads, H) in cases.items():
            fix = {}
            target = cfg["warn_margin"]
            if mg < target:
                def solve(fn, hi):
                    lo_, hi_ = 0.0, hi
                    if fn(hi_) < target:
                        return None
                    for _ in range(60):
                        mid = (lo_ + hi_) / 2
                        if fn(mid) >= target: hi_ = mid
                        else: lo_ = mid
                    return hi_
                fix["move_support_out"] = solve(lambda s: margin(loads, H, shift=s), 2.0)
                fix["move_seat_edge_in"] = solve(lambda s: margin(loads, H, seat_in=s), 2.0) if name != "lean" else None
                fix["ballast_kg"] = solve(lambda b: margin(loads, H, ballast=b), 500.0)
            rows.append(dict(case=name, edge=i, normal=n.tolist(), p0=p0.tolist(), p1=p1.tolist(), margin=mg, rock_deg=math.degrees(th),
                             load_point=(far - e * n).tolist() if name == "edge test" else ((far - cfg["perch_in_mm"] / 1000 * n).tolist() if name == "perch on the edge" else seat_c.tolist()),
                             fix=fix))
        rows.append(dict(case="rock", edge=i, normal=n.tolist(), p0=p0.tolist(), p1=p1.tolist(), rock_deg=math.degrees(th),
                         seat_move=seat_top * sn))
        rows.append(dict(case="push to tip", edge=i, normal=n.tolist(), p0=p0.tolist(), p1=p1.tolist(), H_tip=H_tip,
                         margin=H_tip / H_lean if H_lean > 0 else float("inf")))
    return rows


# ----------------------------------------------------------------------------------------------
# main


def fmt_len(m, units):
    v = m / UNITS[units]
    if units == "in":
        return f"{v:.2f} in"
    return f"{v:.0f} {units}" if units == "mm" else f"{v:.1f} {units}"


def status(margin, warn):
    return "FAIL" if margin < 1.0 else ("WARN" if margin < warn else "PASS")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("--spec", required=True)
    ap.add_argument("--res", type=float, help="voxel size in model units (default: auto, about 120k cells)")
    ap.add_argument("--cells", type=int, default=120000, help="target cell count for auto resolution")
    ap.add_argument("--out", default=None, help="output folder (default: next to the spec)")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--probe", action="append", default=[], help="x,y,z in model units: record the stress there for every case (testing)")
    ap.add_argument("--cases", default=None, help="comma list to run only some strength cases (sit,drop,edge,lean,stand)")
    a = ap.parse_args(argv)
    t0 = time.time()
    spec = json.load(open(a.spec))
    cfg = json.loads(json.dumps(DEFAULTS));
    for k, v in spec.items():
        if k == "sf":
            cfg["sf"].update(v)
        elif k in cfg:
            cfg[k] = v
    units = spec.get("units", "m"); up = spec.get("up", "z"); us = UNITS[units]
    lib = load_materials(); ratios = lib["wood_elastic_ratios"]
    raw = load_parts(a.model, units, up)
    names = list(raw.keys())
    out_dir = a.out or os.path.dirname(os.path.abspath(a.spec))
    os.makedirs(out_dir, exist_ok=True)
    base = spec.get("name") or os.path.splitext(os.path.basename(a.model))[0]
    sha = hashlib.sha256(open(a.model, "rb").read()).hexdigest()[:12] if os.path.isfile(a.model) else "dir"

    # parts
    cfgs = {n: part_config(n, spec) for n in names}
    struct = [n for n in names if cfgs[n]["role"] == "structure"]
    pads = [n for n in names if cfgs[n]["role"] == "pad"]
    if not struct:
        raise SystemExit("no structural parts")
    zmin = min(raw[n].bounds[0, 2] for n in struct)
    for m in raw.values():
        m.vertices = np.asarray(m.vertices) - [0, 0, zmin]
    mats = []
    for n in struct:
        mname = cfgs[n].get("material") or spec.get("material")
        if not mname:
            raise SystemExit(f"no material for part {n}: set 'material' in the spec")
        mat = find_material(mname, lib)
        if mat["kind"] == "metal" and cfgs[n].get("finish", spec.get("finish", "as_built")) == "polished":
            mat["Se"] = mat.get("Se_polished", mat["Se"])
        grain = cfgs[n].get("grain")
        if mat["kind"] == "wood" and not mat.get("isotropic"):
            if grain is None:
                ext = raw[n].extents; grain = "xyz"[int(np.argmax(ext))]
                cfgs[n]["grain_guessed"] = True
        else:
            grain = None
        cfgs[n]["grain"] = grain
        mats.append(dict(mat=mat, grain=grain, D=D_matrix(mat, grain, ratios)))

    # grid
    lo = np.min([raw[n].bounds[0] for n in struct + pads], 0); hi = np.max([raw[n].bounds[1] for n in struct + pads], 0)
    lo[2] = 0.0
    vol = sum(abs(raw[n].volume) for n in struct)
    def thin(m):
        try:
            return float(np.min(m.bounding_box_oriented.primitive.extents))
        except Exception:
            return float(np.min(m.extents))
    tmin = min(thin(raw[n]) for n in struct)
    if a.res:
        h = a.res * us
    else:
        h = (vol / a.cells) ** (1 / 3)
        if tmin / h < 3:
            h = max(tmin / 3, (vol / (3 * a.cells)) ** (1 / 3))
    shape = tuple(int(math.ceil((hi[k] - lo[k]) / h)) + 1 for k in range(3))
    nskip = max(2, int(math.ceil(8e-3 / h)))   # floor contact stresses (bottom 8 mm) are not a part failure
    print(f"[grid] cell {fmt_len(h, units)} ({h*1000:.1f} mm), grid {shape}", flush=True)
    owner = -np.ones(shape, np.int64)
    for pi, n in enumerate(struct):
        occ = voxelize(raw[n], lo, h, shape)
        owner[occ & (owner < 0)] = pi
    pad_owner = -np.ones(shape, np.int64)
    for qi, n in enumerate(pads):
        occ = voxelize(raw[n], lo, h, shape)
        pad_owner[occ & (owner < 0)] = qi
    counts = np.bincount(owner[owner >= 0], minlength=len(struct))
    vox_warn = []
    for pi, n in enumerate(struct):
        mv = abs(raw[n].volume) if raw[n].is_watertight else None
        if mv and counts[pi]:
            r_ = counts[pi] * h ** 3 / mv
            if abs(r_ - 1) > 0.10:
                vox_warn.append(f"{n} comes out {r_*100:.0f}% of its real volume at this cell size, so its stiffness and strength are off; rerun with a finer --res")
    for pi, n in enumerate(struct):
        if counts[pi] == 0:
            print(f"  warning: part {n} is thinner than one cell and was dropped; use a finer --res", flush=True)
    # drop islands that touch nothing (floating bits never reach the floor)
    from scipy.ndimage import label
    lab, nlab = label(owner >= 0)
    if nlab > 1:
        floor_labels = set(np.unique(lab[:, :, 0])) - {0}
        sizes = np.bincount(lab.ravel())
        for L in range(1, nlab + 1):
            if L not in floor_labels:
                print(f"  note: {sizes[L]} cells ({sizes[L]*h**3*1e6:.1f} cm3) don't connect to anything that reaches the floor; "
                      "they're left out of the strength model", flush=True)
                owner[lab == L] = -1
    print(f"[grid] {int((owner>=0).sum())} structural cells, {int((pad_owner>=0).sum())} pad cells, "
          f"{time.time()-t0:.0f}s", flush=True)

    jspecs = spec.get("joints", [])

    def joint_spec(nA, nB):
        for j in jspecs:
            ra, rb = j["between"]
            if (re.search(ra, nA) and re.search(rb, nB)) or (re.search(ra, nB) and re.search(rb, nA)):
                return j
        kinds = {mats[struct.index(nA)]["mat"]["kind"], mats[struct.index(nB)]["mat"]["kind"]}
        return {"type": spec.get("default_joint", "glued" if kinds == {"wood"} else "bolted")}

    pass
    dry_pairs = [(i, j) for i in range(len(struct)) for j in range(i + 1, len(struct))
                 if joint_spec(struct[i], struct[j]).get("type") in DRY]
    model = FEModel(owner, lo, h, struct, mats, dry_pairs)
    print(f"[fe] {model.ne} elements, {3*model.nn} dof, {time.time()-t0:.0f}s", flush=True)

    # masses
    mass = {}; com_num = np.zeros(3)
    for pi, n in enumerate(struct):
        m = raw[n]; V = abs(m.volume) if m.is_watertight else counts[pi] * h ** 3
        mass[n] = V * mats[pi]["mat"]["density"]
        c = m.center_mass if m.is_watertight else m.bounds.mean(0)
        com_num += mass[n] * c
    for n in pads:
        m = raw[n]; V = abs(m.volume) if m.is_watertight else (pad_owner >= 0).sum() * h ** 3 / max(len(pads), 1)
        mass[n] = V * cfgs[n].get("density", lib["pad"]["density"])
        com_num += mass[n] * (m.center_mass if m.is_watertight else m.bounds.mean(0))
    M_tot = sum(mass.values()); com = com_num / M_tot

    # seat
    seat_rx = spec.get("seat")
    seat_parts = [n for n in names if seat_rx and re.search(seat_rx, n)] or pads or \
                 [max(struct, key=lambda n: raw[n].bounds[1, 2])]
    seat_is_pad = all(cfgs[n]["role"] == "pad" for n in seat_parts)
    fp, seat_top = seat_footprint([raw[n] for n in seat_parts], spec.get("seat_band", 0.5) * min(raw[n].extents[2] for n in seat_parts))
    seat_c = np.array(fp.centroid.coords[0])
    seat_struct_ids = {struct.index(n) for n in seat_parts if n in struct}
    print(f"[seat] {', '.join(seat_parts)}: top {fmt_len(seat_top, units)}, footprint {fp.area/us**2:.1f} {units}2", flush=True)

    # ---- strength cases
    from shapely.geometry import Point
    W = cfg["occupant_kg"] * G
    r_sit = cfg["pad_d_mm"] / 2000; r_edge = cfg["edge_pad_d_mm"] / 2000; e_in = cfg["edge_in_mm"] / 1000
    # seat axes from footprint
    fpts = np.vstack([np.array(g.exterior.coords) for g in getattr(fp, "geoms", [fp])])
    _, ev = np.linalg.eigh(np.cov((fpts - seat_c).T))
    axes2 = [ev[:, 1], -ev[:, 1], ev[:, 0], -ev[:, 0]]
    axis_names = []
    for v in axes2:
        k = int(np.argmax(np.abs(v))); axis_names.append(("+" if v[k] > 0 else "-") + "xy"[k])
    cases = []
    cases.append(dict(key="sit", label=f"sit, {cfg['occupant_kg']} kg centred", F=[0, 0, -W], at=seat_c, r=r_sit, sf_kind="static"))
    cases.append(dict(key="drop", label=f"drop in, {cfg['dynamic_factor']} x weight centred", F=[0, 0, -W * cfg["dynamic_factor"]], at=seat_c, r=r_sit))
    for v, nm in zip(axes2, axis_names):
        far = fpts[np.argmax(fpts @ v)]
        at = seat_c + v * ((far - seat_c) @ v - e_in)
        cases.append(dict(key=f"edge{nm}", label=f"sit hard on the {nm} edge, {cfg['edge_factor']} x weight", F=[0, 0, -W * cfg["edge_factor"]], at=at, r=r_edge))
    for v, nm in zip(axes2, axis_names):
        Hv = cfg["lean_frac"] * W * v
        cases.append(dict(key=f"lean{nm}", label=f"lean / rock toward {nm}, weight + {cfg['lean_frac']:.2f} x weight sideways", F=[Hv[0], Hv[1], -W], at=seat_c, r=r_sit))
    if cfg["stand"]:
        cases.append(dict(key="stand", label="stand, 1.5 x weight on a 100 mm pad", F=[0, 0, -1.5 * W], at=seat_c, r=0.05))
        for v, nm in zip(axes2[:2], axis_names[:2]):
            far = fpts[np.argmax(fpts @ v)]
            cases.append(dict(key=f"stand{nm}", label=f"stand on the {nm} end, 1.5 x weight", F=[0, 0, -1.5 * W], at=seat_c + v * ((far - seat_c) @ v - 0.07), r=0.05))
    if a.cases:
        want = a.cases.split(",")
        cases = [c for c in cases if any(c["key"].startswith(w) for w in want)]

    faces = model.faces
    # cuts through one-piece bodies (bolted sections)
    cuts = []
    for c in spec.get("cuts", []):
        P0 = np.array(c["point"], float) * us - [0, 0, zmin]; nv = np.array(c["normal"], float); nv /= np.linalg.norm(nv)
        ctr = model.origin + (model.ijk + 0.5) * h
        inreg = np.linalg.norm(ctr - P0, axis=1) <= c.get("radius", 1e9) * us
        side = (ctr - P0) @ nv > 0
        plus = np.flatnonzero(inreg & side); minus = np.flatnonzero(inreg & ~side)
        shared = np.intersect1d(np.unique(model.enode[plus]), np.unique(model.enode[minus]))
        cuts.append(dict(spec=c, plus=plus, shared=shared, n=nv))
        print(f"[cut] {c.get('name','cut')}: section {len(shared)} nodes", flush=True)

    probes = {}
    part_res = {n: [] for n in struct}; joint_res = {}; cut_res = {}; defl = None; reac = None; fatigue = {}
    sf = cfg["sf"]
    for cs in cases:
        tc = time.time()
        patch = Point(*cs["at"]).buffer(cs["r"], 32).intersection(fp)
        if patch.is_empty:
            patch = Point(*cs["at"]).buffer(cs["r"] * 2, 32).intersection(fp)
        model.supports("friction" if (cs["key"].startswith("lean") or cfg["floor"] == "friction_all") else "slippery")
        Fn = load_columns(model, pad_owner, seat_struct_ids, patch, cs["F"], seat_is_pad)
        f = model.fg.copy()
        for nd, fv in Fn.items():
            f[3 * nd:3 * nd + 3] += fv
        u, its = model.solve(f)
        S, Fint = model.stresses(u)
        Ss = smooth_field(model, S)
        ldn = np.array(list(Fn.keys()))
        for pr in a.probe:
            P_ = np.array([float(v) for v in pr.split(",")]) * us - [0, 0, zmin]
            cx = model.X[model.enode].reshape(-1, 3); kq = int(np.argmin(np.linalg.norm(cx - P_, axis=1)))
            probes.setdefault(pr, {})[cs["key"]] = dict(S_MPa=(Ss.reshape(-1, 6)[kq] / 1e6).round(3).tolist(),
                                                        at=((cx[kq] + [0, 0, zmin]) / us).round(2).tolist())
        if cs["key"] == "sit":
            defl = float(-u[3 * ldn + 2].mean()); defl_max = float(-u[3 * ldn + 2].min())
            fl0 = model.floor_nodes
            ux = u[3 * fl0]; uy = u[3 * fl0 + 1]
            reac = dict(spread_mm=float(max(np.ptp(ux), np.ptp(uy)) * 1000))
        if False:
            R = model.K @ u - f
            fl = model.floor_nodes
            reac = dict(V=float(R[3 * fl + 2].sum()), H=float(np.hypot(R[3 * fl].sum(), R[3 * fl + 1].sum())))
            from scipy.ndimage import label as lab2
            m2 = np.zeros(model.shape[:2], bool); m2[model.nijk[fl, 0].clip(0, model.shape[0] - 1), model.nijk[fl, 1].clip(0, model.shape[1] - 1)] = True
            L2, nL = lab2(m2, np.ones((3, 3)))
            lbl = L2[model.nijk[fl, 0].clip(0, model.shape[0] - 1), model.nijk[fl, 1].clip(0, model.shape[1] - 1)]
            ratios_ = []
            for L in range(1, nL + 1):
                s_ = fl[lbl == L]
                Vf = R[3 * s_ + 2].sum(); Hf = np.hypot(R[3 * s_].sum(), R[3 * s_ + 1].sum())
                if Vf > 1: ratios_.append(Hf / Vf)
            reac["max_H_over_V"] = float(max(ratios_)) if ratios_ else 0.0
        # parts
        for pi, n in enumerate(struct):
            sel = np.flatnonzero((model.epart == pi) & (model.ijk[:, 2] >= nskip))
            if len(sel) == 0:
                continue
            mat = mats[pi]["mat"]; ctr = model.X[model.enode[sel]].reshape(-1, 3)
            Sf = Ss[sel].reshape(-1, 6)
            if mat["kind"] == "wood" and not mat.get("isotropic"):
                ut, mode = wood_util(Sf, mats[pi]["grain"], mat, sf["crush_perp"] / sf["wood"])
                req = sf["wood"]
            elif mat["kind"] == "wood":
                ut = von_mises(Sf) / (mat["MOR"] * 1e6); mode = np.array(["combined"] * len(Sf)); req = sf["wood"]
            else:
                ut = von_mises(Sf) / (mat["fy"] * 1e6); mode = np.array(["yield (von Mises)"] * len(Sf)); req = sf["metal"]
            k = int(np.argmax(ut))
            row = dict(case=cs["key"], label=cs["label"], util=float(ut[k] * req), raw_sf=float(1 / max(ut[k], 1e-12)), req=req,
                       mode=str(mode[k]), at=((ctr[k] + [0, 0, zmin]) / us).round(2).tolist(),
                       stress_MPa=float(von_mises(Sf[k:k + 1])[0] / 1e6))
            # wood: axial crush and buckling along the grain, from slice averages
            if mat["kind"] == "wood" and mats[pi]["grain"]:
                ax = "xyz".index(mats[pi]["grain"])
                sl = model.ijk[sel, ax]; sL = S[sel].mean(1)[:, ax]
                means = np.bincount(sl - sl.min(), weights=sL) / np.maximum(np.bincount(sl - sl.min()), 1)
                cnt = np.bincount(sl - sl.min())
                good = cnt > 0.5 * np.median(cnt[cnt > 0])
                comp = -means[good].min() if good.any() else 0
                row["axial_util"] = float(max(comp, 0) / (mat["fc_par"] * 1e6) * req)
                # Euler buckling of the part as a pinned strut, smallest section
                Nsl = np.bincount(sl - sl.min(), weights=sL) * h * h
                nsl = len(Nsl); mid = np.arange(int(0.15 * nsl), max(int(0.85 * nsl), int(0.15 * nsl) + 1))
                Pcomp = max(-Nsl[mid].min(), 0) if len(mid) else 0
                L = (sl.max() - sl.min() + 1) * h
                Imin = 1e9
                for s_ in (sl.min() + mid)[::max(1, len(mid) // 12)]:
                    q = model.ijk[sel][sl == s_][:, [k_ for k_ in range(3) if k_ != ax]] * h
                    if len(q) < 4: continue
                    A = len(q) * h * h; cq = q.mean(0); C = np.cov((q - cq).T, bias=True) * A + np.eye(2) * A * h * h / 12
                    Imin = min(Imin, np.linalg.eigvalsh(C)[0])
                Pcr = math.pi ** 2 * mat["E"] * 1e6 * Imin / L ** 2 if Imin < 1e9 else float("inf")
                row["buckle_util"] = float(Pcomp / Pcr * req) if Pcr > 0 else 0.0
            part_res[n].append(row)
            if mat["kind"] == "metal" and cs["key"] == "sit":
                pm = principal_max(Sf); kk = int(np.argmax(pm))
                Se = mat["Se"]; fu = mat["fu"]
                allow = 2 / (1 / Se + 1 / fu)  # Goodman, 0 -> max cycling
                fatigue[n] = dict(util=float(pm[kk] / 1e6 / allow * sf["fatigue"]), stress_MPa=float(pm[kk] / 1e6), allow_MPa=allow,
                                  at=((ctr[kk] + [0, 0, zmin]) / us).round(2).tolist(), Se=Se)
        # joints between parts
        for (pA, pB), fl_ in faces.items():
            nA, nB = struct[pA], struct[pB]
            js = joint_spec(nA, nB); typ = js.get("type", "glued")
            key = f"{nA} ~ {nB}"
            elA = np.flatnonzero(model.epart == pA); elB = np.flatnonzero(model.epart == pB)
            if typ in DRY and model.spr is not None:
                sm = model.spr["pair"] == (pA << 16) + pB
                Fs = model.spring_forces(u)[sm]; Xs = model.X[model.spr["a"][sm]]
                c = Xs.mean(0); F = Fs.sum(0); M = np.cross(Xs - c, Fs).sum(0)
                shared = np.unique(model.spr["a"][sm])
            else:
                shared = np.intersect1d(np.unique(model.enode[elA]), np.unique(model.enode[elB]))
                F, M, c = resultant(model, Fint, elA, shared)
            d = fl_[:, 0]; ea = fl_[:, 1]; eb = fl_[:, 2]
            sig = np.zeros((len(d), 6))
            for dd in range(3):
                q = d == dd
                if q.any():
                    sig[q] = (Ss[ea[q]][:, LOC[:, dd] == 1].mean(1) + Ss[eb[q]][:, LOC[:, dd] == 0].mean(1)) / 2
            nidx = d; sn = sig[np.arange(len(d)), nidx]
            shear_idx = np.array([[SHEAR_IDX[tuple(sorted((dd, o)))] for o in range(3) if o != dd] for dd in d])
            tau = np.sqrt(sig[np.arange(len(d)), shear_idx[:, 0]] ** 2 + sig[np.arange(len(d)), shear_idx[:, 1]] ** 2)
            area = h * h
            ga = mats[pA]["grain"]; gb = mats[pB]["grain"]
            endg = np.zeros(len(d), bool)
            if ga: endg |= d == "xyz".index(ga)
            if gb: endg |= d == "xyz".index(gb)
            row = dict(case=cs["key"], label=cs["label"], type=typ, F_N=float(np.linalg.norm(F)), M_Nm=float(np.linalg.norm(M)), F_vec=np.round(F, 1).tolist(),
                       contact_area_cm2=float(len(d) * area * 1e4))
            mA, mB = mats[pA]["mat"], mats[pB]["mat"]
            if typ == "glued" and mA["kind"] == "wood" and mB["kind"] == "wood":
                fv = min(mA["fv"], mB["fv"]) * 1e6; ft = min(mA["ft_perp"], mB["ft_perp"]) * 1e6
                load_face = (np.maximum(sn, 0) + tau) * area
                frac_end = float(load_face[endg].sum() / max(load_face.sum(), 1e-9))
                lg = ~endg
                if lg.any():
                    u_face = np.maximum(np.maximum(sn[lg], 0) / ft, tau[lg] / fv)
                    k = int(np.argmax(u_face))
                    boost = 1 / max(1 - frac_end, 0.25)
                    row.update(util=float(u_face[k] * boost * sf["glue"]), end_grain_share=frac_end,
                               mode="glue line: " + ("pulling apart across the grain" if np.maximum(sn[lg], 0)[k] / ft > tau[lg][k] / fv else "shear"))
                else:
                    dem = float(load_face.sum()); Fm = float(np.linalg.norm(F))
                    bad = dem > max(0.05 * Fm, 20.0)
                    row.update(util=(dem / max(0.05 * Fm, 20.0)) if bad else 0.0, end_grain_share=1.0,
                               mode="all end grain: glue alone won't hold it" if bad else "end grain, bearing in compression only")
            elif typ in DRY:
                sm = model.spr["pair"] == (pA << 16) + pB
                Fs = model.spring_forces(u)[sm]; dd_ = model.spr["d"][sm]; sg_ = model.spr["s"][sm]
                Fn_ = Fs[np.arange(len(dd_)), dd_] * sg_       # + = pressing A toward... sign: B pushes A away = compression
                C = float(np.maximum(-Fn_, 0).sum() if False else np.abs(Fn_).sum())
                Ft = float(np.linalg.norm(Fs.sum(0) - (Fs * np.eye(3)[dd_]).sum(0)))
                Fm = float(np.linalg.norm(F))
                kept = float(model.active[sm].mean()) if sm.any() else 0.0
                mu = js.get("mu", 0.4)
                ratio = Ft / max(mu * C, 0.05 * cfg["occupant_kg"] * G)   # under 5% of the sitter's weight sideways is noise
                lost = ((pA << 16) + pB) in getattr(model, "lifted", set())
                row.update(util=99.0 if lost else ratio * 1.0, C_N=C, T_slide_N=Ft, contact_kept=kept,
                           mode=("lifts off completely" if lost else
                                 f"bears on {kept*100:.0f}% of the contact; sideways {Ft:.0f} N vs friction {mu} x {C:.0f} N"))
                fast = js.get("fastener")
                if fast:
                    row["mode"] += f" (held by {fast})"; row["util"] = 0.0 if not js.get("check_fastener") else row["util"]
            elif typ in ("bolted", "screwed"):
                P = model.X[shared]; c0, nrm, maj, mnr = plane_basis(P)
                cA = model.origin + (model.ijk[elA] + 0.5) * h; cB = model.origin + (model.ijk[elB] + 0.5) * h
                n_ab = nrm if (cB.mean(0) - cA.mean(0)) @ nrm > 0 else -nrm
                row.update(bolt_check(js, F, M, c, n_ab, P, maj, mnr, lib, sf, us, mA, mB))
            else:   # welded / fused / unknown: strength is in the parts
                row.update(util=0.0, mode="treated as one piece")
            joint_res.setdefault(key, []).append(row)
        for ct in cuts:
            F, M, c = resultant(model, Fint, ct["plus"], ct["shared"])
            P = model.X[ct["shared"]]; c0, nrm, maj, mnr = plane_basis(P)
            n_ab = -ct["n"]          # force on the + side from the - side; tension pulls + toward -... sign set so + = opening
            mat0 = mats[0]["mat"]
            r = bolt_check(ct["spec"], F, M, c, n_ab, P, maj, mnr, lib, sf, us, mat0, mat0)
            r.update(case=cs["key"], label=cs["label"], F_N=float(np.linalg.norm(F)), M_Nm=float(np.linalg.norm(M)))
            cut_res.setdefault(ct["spec"].get("name", "cut"), []).append(r)
        print(f"[case] {cs['key']:<9} {its:>3} it, {time.time()-tc:5.1f}s", flush=True)
        if cs["key"] == "sit":
            env_sit = None
        # envelope for the sheet
        if "env" not in locals():
            env = np.zeros(model.ne)
        for pi, n in enumerate(struct):
            sel = np.flatnonzero(model.epart == pi)
            if not len(sel): continue
            mat = mats[pi]["mat"]
            if mat["kind"] == "wood" and not mat.get("isotropic"):
                ut, _ = wood_util(Ss[sel].reshape(-1, 6), mats[pi]["grain"], mat, sf["crush_perp"] / sf["wood"]); ut = ut * sf["wood"]
            elif mat["kind"] == "wood":
                ut = von_mises(Ss[sel].reshape(-1, 6)) / (mat["MOR"] * 1e6) * sf["wood"]
            else:
                ut = von_mises(Ss[sel].reshape(-1, 6)) / (mat["fy"] * 1e6) * sf["metal"]
            ut = ut.reshape(-1, 8).max(1); ut[model.ijk[sel, 2] < nskip] = 0
            env[sel] = np.maximum(env[sel], ut)

    # ---- tipping
    from shapely.geometry import MultiPoint
    bot = []
    for n in struct:
        v = np.asarray(raw[n].vertices); bot.append(v[v[:, 2] < max(cfg["rock_tol_mm"], cfg["floor_tol_mm"]) / 1000])
    bot = np.vstack(bot)
    rest = MultiPoint(bot[bot[:, 2] < cfg["floor_tol_mm"] / 1000][:, :2]).convex_hull
    hull, rdirs = settled_footprint(bot, cfg["rock_max_deg"])
    rocks = rest.area < 0.8 * hull.area
    if not rocks:
        hull = rest
    tip = tipping(hull, com[:2], M_tot, fp, seat_top, cfg, us, com_z=com[2], bottom=rdirs if rocks else None)

    # ---- assemble report
    res = dict(model=os.path.abspath(a.model), sha=sha, spec=os.path.abspath(a.spec), units=units, cell_mm=h * 1000,
               elements=model.ne, mass_kg=M_tot, com=((com + [0, 0, zmin]) / us).round(2).tolist(), seat_top=seat_top / us,
               occupant_kg=cfg["occupant_kg"], parts={}, joints={}, cuts={}, fatigue=fatigue, tipping=tip,
               deflection_mm=None if defl is None else defl * 1000, reactions=reac, cfg=cfg)
    for n in struct:
        res["parts"][n] = dict(material=mats[struct.index(n)]["mat"]["name"], grain=cfgs[n].get("grain"),
                               grain_guessed=cfgs[n].get("grain_guessed", False), mass_kg=mass[n], cases=part_res[n])
    res["joints"] = joint_res; res["cuts"] = cut_res; res["probes"] = probes; res["voxel_warnings"] = vox_warn
    res["lifted"] = [f"{struct[p >> 16]} ~ {struct[p & 0xFFFF]}" for p in getattr(model, "lifted", set())]
    res["pads"] = {n: dict(mass_kg=mass[n]) for n in pads}
    rows = summarize(res, cfg, units)
    res["summary"] = rows
    jpath = os.path.join(out_dir, base + ".seatcheck.json")
    json.dump(res, open(jpath, "w"), indent=1, default=float)
    md = report_md(res, rows, cfg, units, base)
    mpath = os.path.join(out_dir, base + ".seatcheck.md")
    open(mpath, "w").write(md)
    if not a.no_sheet:
        try:
            import seatsheet
            seatsheet.make(model, env, res, rows, hull, fp, com, tip, os.path.join(out_dir, base + ".seatcheck.png"), units, zmin, base)
        except Exception as ex:
            print("  sheet failed:", ex)
    print(md)
    print(f"[done] {time.time()-t0:.0f}s -> {mpath}")
    worst = min((r["margin"] for r in rows), default=99)
    return 1 if worst < 1.0 else 0


def bolt_check(js, F, M, c, n_ab, P, maj, mnr, lib, sf, us, mA, mB):
    typ = js.get("type", "bolted")
    if typ == "screwed":
        sc = js.get("screw", {})
        D_in = sc.get("D_in", 0.19); Lt = sc.get("thread_in", 1.0); count = sc.get("count", 2)
        Gw = min(mA.get("density", 500), mB.get("density", 500)) / 1000
        Wlb = 2850 * Gw ** 2 * D_in * Lt
        cap = Wlb * 4.448
        pos, fits = auto_bolts(P, None, maj, mnr, count, D_in * 0.0254)
        if "at" in js: pos = np.array(js["at"], float) * us
        T, V = bolt_group(F, M, c, n_ab, pos)
        Tm = float(max(T.max(), 0))
        return dict(type="screwed", util=Tm / cap * sf["screw"], mode=f"screw withdrawal ({count} x {D_in} in, {Lt} in thread)",
                    T_max_N=Tm, cap_N=cap, fits=fits)
    size = js.get("bolt", "M6"); grade = js.get("grade", "A2-70"); count = js.get("count", 2)
    As = lib["bolts"]["sizes"][size] * 1e-6; g = lib["bolts"]["grades"][grade]
    d = math.sqrt(As * 4 / math.pi) * 1.15
    if "at" in js:
        pos = np.array(js["at"], float) * us; fits = True
    else:
        pos, fits = auto_bolts(P, None, maj, mnr, count, d)
    count = len(pos)
    T, V = bolt_group(F, M, c, n_ab, pos, js["pry_mm"] / 1000 if "pry_mm" in js else 2.5 * d)
    Tc = As * g["fy"] * 1e6; Vc = 0.6 * g["fu"] * 1e6 * As
    ut = np.sqrt((np.maximum(T, 0) / Tc) ** 2 + (V / Vc) ** 2) * sf["bolt"]
    k = int(np.argmax(ut))
    # what would it take
    need = None
    for sz in ("M4", "M5", "M6", "M8", "M10", "M12"):
        As2 = lib["bolts"]["sizes"][sz] * 1e-6
        u2 = np.sqrt((np.maximum(T, 0) / (As2 * g["fy"] * 1e6)) ** 2 + (V / (0.6 * g["fu"] * 1e6 * As2)) ** 2).max() * sf["bolt"]
        if u2 < 1 / 1.2:
            need = sz; break
    return dict(type="bolted", util=float(ut[k]), mode=f"{count} x {size} {grade}: tension {max(T[k],0):.0f} N, shear {V[k]:.0f} N on the worst bolt",
                T_max_N=float(max(T.max(), 0)), V_max_N=float(V.max()), fits=fits, auto_placed="at" not in js, need=need)


def summarize(res, cfg, units):
    rows = []; warn = cfg["warn_margin"]
    for n, p in res["parts"].items():
        if not p["cases"]: continue
        w = max(p["cases"], key=lambda r: r["util"])
        rows.append(dict(group="strength", item=n, case=w["label"], margin=1 / max(w["util"], 1e-9),
                         detail=f"{w['mode']}, at {w['at']} ({p['material']}, safety factor {w['req']} wanted, {w['raw_sf']:.1f} there)",
                         util=w["util"], at=w["at"], mode=w["mode"]))
        if "axial_util" in w or any("axial_util" in r for r in p["cases"]):
            wa = max(p["cases"], key=lambda r: r.get("axial_util", 0))
            if wa.get("axial_util", 0) > 0.25:
                rows.append(dict(group="strength", item=n + " (crush along grain)", case=wa["label"], margin=1 / max(wa["axial_util"], 1e-9), detail="average compression over the section"))
            wb = max(p["cases"], key=lambda r: r.get("buckle_util", 0))
            if wb.get("buckle_util", 0) > 0.25:
                rows.append(dict(group="strength", item=n + " (buckling)", case=wb["label"], margin=1 / max(wb["buckle_util"], 1e-9), detail="pinned-end Euler, thinnest section"))
    for n, f in res["fatigue"].items():
        rows.append(dict(group="fatigue", item=n, case="everyday sit, repeated", margin=1 / max(f["util"], 1e-9),
                         detail=f"{f['stress_MPa']:.0f} MPa peak vs {f['allow_MPa']:.0f} MPa allowed for 0-to-peak cycling (Goodman, Se {f['Se']} MPa), at {f['at']}"))
    for k, rs in list(res["joints"].items()) + list(res["cuts"].items()):
        w = max(rs, key=lambda r: r.get("util", 0))
        if w.get("type") in ("welded", "fused") or w.get("mode") == "treated as one piece":
            continue
        extra = ""
        if "end_grain_share" in w: extra = f", {w['end_grain_share']*100:.0f}% of the load on end grain"
        if w.get("auto_placed"): extra += ", bolt positions assumed" + ("" if w.get("fits", True) else ", BOLTS DON'T FIT THE SECTION")
        rows.append(dict(group="joint", item=k, case=w["label"], margin=1 / max(w.get("util", 0), 1e-9),
                         soft=(w.get("type") in DRY and w.get("util", 0) < 99),     # a resting joint that slides: WARN; one that lifts off: FAIL
                         detail=f"{w.get('type')}: {w.get('mode','')}{extra}; carries {w['F_N']:.0f} N, {w['M_Nm']:.0f} N m",
                         need=w.get("need"), raw=w))
    for case in ("edge test", "perch on the edge", "lean"):
        rs = [r for r in res["tipping"] if r["case"] == case]
        if not rs: continue
        w = min(rs, key=lambda r: r["margin"])
        mg = w["margin"]
        if case == "perch on the edge" and not cfg["perch_must_hold"]:
            mg = max(mg, 1.0)
        rows.append(dict(group="tipping", item=case, case=f"over the edge facing {fmt_dir(w['normal'])}",
                         margin=mg, detail=tip_detail(w, case, cfg, units), fix=w.get("fix"), raw=w))
    rs = [r for r in res["tipping"] if r["case"] == "rock" and r["rock_deg"] > 0]
    if rs:
        w = max(rs, key=lambda r: r["seat_move"])
        mv = w["seat_move"] * 1000
        rows.append(dict(group="stability", item="rocks on its feet", case=f"toward {fmt_dir(w['normal'])}",
                         margin=cfg["rock_warn_mm"] / max(mv, 1e-9),
                         detail=f"the feet aren't flat: it stands on a narrow strip and can rock up to {w['rock_deg']:.1f} deg ({mv:.0f} mm at the seat) "
                                f"onto the rest of its feet; tipping is checked after it has rocked. Flatten the feet or add glides",
                         soft=True))
    rs = [r for r in res["tipping"] if r["case"] == "push to tip"]
    if rs:
        w = min(rs, key=lambda r: r["H_tip"])
        rows.append(dict(group="tipping", item="push to tip (seated)", case=f"toward {fmt_dir(w['normal'])}", margin=w["margin"],
                         detail=f"{w['H_tip']:.0f} N ({w['H_tip']/4.448:.0f} lbf) sideways at the seat tips it with a {cfg['occupant_kg']} kg sitter; lean case asks for {cfg['lean_frac']:.2f} x weight"))
    if res["deflection_mm"] is not None:
        d = res["deflection_mm"]
        rows.append(dict(group="stiffness", item="seat sink", case="sit", margin=cfg["deflection_warn_mm"] / max(d, 1e-9) if d > 0 else 99,
                         detail=f"{d:.1f} mm under the sitter (warns past {cfg['deflection_warn_mm']} mm: feels bouncy)", soft=True))
    if res["reactions"] and res["reactions"].get("spread_mm", 0) > 0.5:
        r = res["reactions"]["spread_mm"]
        rows.append(dict(group="stability", item="feet spreading", case="sit, slippery floor", margin=2.0 / r,
                         detail=f"the feet move {r:.1f} mm apart on a slippery floor (warns past 2 mm)", soft=True))
    for r in rows:
        r["status"] = status(r["margin"], warn)
        if r.get("soft") and r["status"] == "FAIL":
            r["status"] = "WARN"
    return rows


def fmt_dir(n):
    a = math.degrees(math.atan2(n[1], n[0])) % 360
    names = ["+x", "+x+y", "+y", "-x+y", "-x", "-x-y", "-y", "+x-y"]
    return names[int(((a + 22.5) % 360) // 45)]


def tip_detail(w, case, cfg, units):
    s = {"edge test": f"{cfg['tip_edge_N']} N {cfg['edge_in_mm']} mm in from the seat edge + {cfg['tip_edge_push_N']} N outward",
         "perch on the edge": f"the whole {cfg['occupant_kg']} kg perched {cfg['perch_in_mm']} mm in from the seat edge",
         "lean": f"{cfg['occupant_kg']} kg centred, pushing {cfg['lean_frac']:.2f} x weight outward at seat height"}[case]
    f = w.get("fix") or {}
    bits = []
    if f.get("move_support_out") is not None: bits.append(f"feet out {fmt_len(f['move_support_out'], units)}")
    if f.get("move_seat_edge_in") is not None: bits.append(f"seat edge in {fmt_len(f['move_seat_edge_in'], units)}")
    if f.get("ballast_kg") is not None: bits.append(f"{f['ballast_kg']:.1f} kg low in the base")
    return s + ("; to reach " + str(cfg["warn_margin"]) + ": " + " or ".join(bits) if bits else "")


def fixes(rows, res, cfg, units):
    out = []
    for r in rows:
        if r["status"] == "PASS":
            continue
        m = r["margin"]; ratio = 1 / m * cfg["warn_margin"]
        if r["group"] == "strength" and "crush" not in r["item"] and "buckl" not in r["item"]:
            mode = r.get("mode", "")
            if "across the grain" in mode and "tension" in mode:
                out.append(f"{r['item']}: the load pulls across the grain near {r.get('at')} (it would split). Change the grain direction, "
                           f"move the joint, or pin across it with a bolt or dowel; more wood helps only about x{ratio:.2f}.")
            elif "crushing" in mode:
                out.append(f"{r['item']}: crushing across the grain near {r.get('at')}. Spread the bearing area about x{ratio:.2f} (wider seat for the part, washer, or bearing block).")
            elif "shear" in mode:
                out.append(f"{r['item']}: {mode} near {r.get('at')}. Give it about x{ratio:.2f} more section across the shear, or shorten the span.")
            elif "yield" in mode:
                out.append(f"{r['item']}: metal over its allowed stress near {r.get('at')}. Thicken there about x{math.sqrt(ratio):.2f} in the bending direction "
                           f"(+{(math.sqrt(ratio)-1)*100:.0f}%), add a fillet, or bring a support closer.")
            else:
                out.append(f"{r['item']}: bending near {r.get('at')}. Make it about x{math.sqrt(ratio):.2f} deeper in the bending direction "
                           f"(+{(math.sqrt(ratio)-1)*100:.0f}%), or x{ratio:.2f} wider, or add a brace closer to the load.")
        elif "crush" in r["item"]:
            out.append(f"{r['item']}: grow the section about x{ratio:.2f}.")
        elif "buckl" in r["item"]:
            out.append(f"{r['item']}: stiffen the thin direction about x{ratio**(1/3):.2f} or brace it at mid-length.")
        elif r["group"] == "fatigue":
            out.append(f"{r['item']}: fatigue under everyday sitting. Polish / machine that area (raises the fatigue limit about 2x on printed metal), "
                       f"thicken it about x{math.sqrt(ratio):.2f}, or add a fillet.")
        elif r["group"] == "joint":
            w = r.get("raw", {})
            if w.get("type") == "glued":
                if w.get("end_grain_share", 0) > 0.3:
                    out.append(f"{r['item']}: leans on end-grain glue ({w['end_grain_share']*100:.0f}%). Give it long-grain cheeks (a real tenon or bridle) or a mechanical fastener.")
                else:
                    out.append(f"{r['item']}: glue line about x{ratio:.2f} short. Longer or wider tenon, a second tenon, drawbore pin, or a bolt.")
            elif w.get("type") == "dry":
                out.append(f"{r['item']}: the dry joint pulls apart ({w.get('T_open_N',0):.0f} N trying to open it). Glue it, pin it, or bolt it.")
            elif w.get("type") == "bolted":
                need = w.get("need")
                out.append(f"{r['item']}: bolts over. " + (f"Go to {need} at the same spacing" if need else "Spread the bolts further apart or add more")
                           + ("" if w.get("fits", True) else "; the section is too small for these bolts as placed") + ".")
            elif w.get("type") == "screwed":
                out.append(f"{r['item']}: screws would pull out. More or longer screws, or swap to a bolt / threaded insert.")
        elif r["group"] == "tipping":
            out.append(f"Tipping, {r['item']} {r['case']}: " + r["detail"].split("; to reach")[-1].strip() + ".")
        elif r["group"] == "stiffness":
            out.append("Seat sink: stiffen the seat rail (deeper section) or shorten the span.")
        elif r["group"] == "stability":
            out.append("Feet push outward: add a low stretcher between the feet or rubber pads.")
    return out


def report_md(res, rows, cfg, units, base):
    worst = min((r["margin"] for r in rows), default=99)
    verdict = "FAIL" if any(r["status"] == "FAIL" for r in rows) else ("PASS with warnings" if any(r["status"] == "WARN" for r in rows) else "PASS")
    L = [f"# Seat check: {base}", "",
         f"**{verdict}.** Lowest margin {worst:.2f} (1.00 is the line). Model `{os.path.basename(res['model'])}` sha {res['sha']}, "
         f"{res['elements']} cells of {res['cell_mm']:.1f} mm. Piece weighs {res['mass_kg']:.1f} kg; seat top {res['seat_top']:.2f} {units}. "
         f"Design sitter {cfg['occupant_kg']} kg.", "",
         "| | Check | Case | Margin | Notes |", "|---|---|---|---|---|"]
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    for r in sorted(rows, key=lambda r: (order[r["status"]], r["margin"])):
        L.append(f"| {r['status']} | {r['group']}: {r['item']} | {r['case']} | {min(r['margin'], 99):.2f} | {r['detail']} |")
    fx = fixes(rows, res, cfg, units)
    for w_ in res.get("voxel_warnings", []):
        L.insert(3, f"**Resolution: {w_}.**\n")
    if res.get("lifted"):
        L.insert(3, f"**A resting joint comes apart under load ({', '.join(res['lifted'])}), so the piece isn't held together there. "
                    "Fix that first: the stresses next to it are not meaningful until it is.**\n")
    L += ["", "## Fixes", ""] + ([f"- {f}" for f in fx] if fx else ["- None needed."])
    L += ["", "## Parts", "", "| Part | Material | Grain | Mass kg |", "|---|---|---|---|"]
    for n, p in res["parts"].items():
        L.append(f"| {n} | {p['material']} | {p['grain'] or '-'}{' (guessed)' if p['grain_guessed'] else ''} | {p['mass_kg']:.2f} |")
    for n, p in res.get("pads", {}).items():
        L.append(f"| {n} | pad (no stiffness, passes load down) | - | {p['mass_kg']:.2f} |")
    L += ["", "## What it assumed", "",
          f"- Safety factors wanted: wood {cfg['sf']['wood']} on mean clear-wood strength, metal {cfg['sf']['metal']} on yield, glue {cfg['sf']['glue']}, bolts {cfg['sf']['bolt']}, fatigue {cfg['sf']['fatigue']}.",
          f"- Loads: sit {cfg['occupant_kg']} kg on a {cfg['pad_d_mm']} mm pad; drop {cfg['dynamic_factor']}x; edges {cfg['edge_factor']}x on a {cfg['edge_pad_d_mm']} mm pad {cfg['edge_in_mm']} mm in; lean {cfg['lean_frac']} x weight sideways at seat height"
          + ("; standing 1.5x on 100 mm" if cfg["stand"] else "") + ".",
          f"- Floor: slippery for the sit, drop and edge cases (feet free to spread), gripping for the lean cases. Joints that touch are bonded in the stiffness model; glued, dry and bolted joints are then checked from the forces they carry.",
          "- Wood is clear, straight grain at 12% moisture. Knots, runout and short grain are not seen: look at the boards.",
          "- Voxel stresses at sharp inside corners depend on the cell size. Rerun at a finer --res and trust what holds at both."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main())
