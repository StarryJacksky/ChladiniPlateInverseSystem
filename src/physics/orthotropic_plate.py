from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""Differentiable orthotropic Kirchhoff plate with per-cell infill angle θ.
可微正交各向异性 Kirchhoff 板，按格子定义 infill 方向 θ。

物理动机 / Physics motivation:
让每个 15×15 格子的"主刚度方向" θ 独立可优化，θ(x,y) 是非对称场（默认非 D4），
整块板的弯曲刚度算子也非 D4 对称 —— **物理层面**打破 D4 对称（不靠 SBS 数值 hack）。
D∞-center-excitation 不再被限制于 A1 irrep，因为算子本身不再 commute 于 D4 群。

材料选择 / Material consideration:
- **SLA grey resin（用户当前选择）实际上接近各向同性**（Formlabs 2018, Sci. Reports 2025）：
  E_||/E_⊥ 通常 1.00–1.10，因为 SLA 共价键跨层连续；
  → 默认 stiffness_ratio=1.05（接近各向同性的保守上限）
  → 在该参数下 D4 物理破坏很弱（θ 优化空间小）
- **FDM PLA 才有强各向异性**（Letcher & Waytashek 2014）：E_||/E_⊥ ≈ 1.3–2.0
  → 如果客户换 FDM PLA 可将 stiffness_ratio 调到 1.5–2.0
- **碳纤+短纤增强树脂**：可达 2.0–4.0
- 实际值请在前端 Material panel 的 Stiffness ratio E∥/E⊥ 输入框调整

Kirchhoff-Love 正交各向异性板的应变能密度 / Strain-energy density:
U = (1/2) [D11 w_xx² + 2 D12 w_xx w_yy + D22 w_yy² + 4 D66 w_xy²]
    + 2 D16 w_xx w_xy + 2 D26 w_yy w_xy            (off-axis terms appear when θ ≠ 0, π/2)

其中 D11, D22 是主弯曲刚度，D12 是横向耦合，D66 是扭转刚度。
D16, D26 由 θ 引入，是真正的"非 D4"项。

材料常数推导 / Material constants derivation (输入 E_pa, stiffness_ratio sr):
- E_|| = E_pa × sqrt(sr)
- E_⊥ = E_pa / sqrt(sr)
- ν_⊥|| = ν_|| × (E_⊥ / E_||) （Maxwell-Betti 互易性 / Reciprocity）
- G_|| = G_iso × shear_ratio，G_iso = E_pa / (2(1+ν))

参考 / References:
- Formlabs 2018 "Validating Isotropy in SLA 3D Printing" (E_||/E_⊥ ≈ 1.0)
- Sci. Reports 15:97294 (2025) – vat photopolymerisation anisotropy ≈ 0–10% post-cure
- Letcher & Waytashek 2014 (FDM PLA tensile, E_||/E_⊥ ≈ 1.4)
- Pyl et al. 2018 (Procedia Manufacturing 14:104 – FDM test methodology)
- Reddy 2003 (Mechanics of Laminated Composite Plates and Shells)
"""

import torch  # Torch / Torch


class OrthotropicPlate:  # 可微正交各向异性 KL 板 / Differentiable orthotropic KL plate
    def __init__(self, config: dict, proxy_grid_size: int = 25, base_accel: float = 1.0, default_damping: float = 0.02, reference_frequency_hz: float = 600.0, stiffness_ratio: float | None = None, shear_ratio: float | None = None, dtype: torch.dtype = torch.float64, device: str | torch.device = "cpu") -> None:  # 初始化 / Init
        self.config = config  # 配置 / Config
        self.N = int(proxy_grid_size)  # 代理网格 / Proxy grid
        if self.N % 2 == 0:  # 强制奇数 / Force odd
            self.N += 1  # 自增 / Increment
        self.dtype = dtype  # 浮点 / Float
        self.cdtype = torch.complex128 if dtype == torch.float64 else torch.complex64  # 复数 / Complex
        self.device = torch.device(device)  # 设备 / Device
        plate_length_mm = float(config["project"]["plate_length_mm"])  # 板长 / Length
        plate_width_mm = float(config["project"]["plate_width_mm"])  # 板宽 / Width
        self.plate_length_mm = plate_length_mm  # 保存 / Store
        self.dx_m = plate_length_mm * 1.0e-3 / float(self.N)  # x cell / x cell
        self.dy_m = plate_width_mm * 1.0e-3 / float(self.N)  # y cell / y cell
        self.cell_area_m2 = self.dx_m * self.dy_m  # 面积 / Area
        material = config.get("material", {})  # 材料 / Material
        E_pa = float(material.get("youngs_modulus_pa", 2.0e9))  # 模量 / Modulus
        nu = float(material.get("poisson_ratio", 0.35))  # 泊松 / Poisson
        self.rho_kg_m3 = float(material.get("density_kg_m3", 1200.0))  # 密度 / Density
        # 各向异性参数：优先用 explicit kwarg，否则从 config.material 读，再否则用 SLA grey resin 默认 1.05
        # Anisotropy: prefer explicit kwarg, then config.material, then SLA grey resin default 1.05
        if stiffness_ratio is None:  # 未传 / Not passed
            stiffness_ratio = float(material.get("stiffness_ratio", 1.05))  # 默认 1.05 (SLA grey resin) / Default 1.05 (SLA grey resin)
        if shear_ratio is None:  # 未传 / Not passed
            shear_ratio = float(material.get("shear_ratio", 1.0))  # 默认 1.0 (各向同性) / Default 1.0 (isotropic)
        # 正交各向异性主轴材料常数 / Orthotropic principal-axis constants
        sr = max(float(stiffness_ratio), 1.0)  # 各向异性比 (沿丝方向更硬) / Stiffness ratio (stiffer along fibre)
        self.stiffness_ratio = sr  # 保存以便诊断 / Store for diagnostics
        self.shear_ratio = float(shear_ratio)  # 保存 / Store
        self.E_parallel_pa = E_pa * (sr ** 0.5)  # E_|| / E_parallel
        self.E_perp_pa = E_pa / (sr ** 0.5)  # E_⊥ / E_perp
        self.nu_pp = nu  # 主泊松比 / Principal Poisson
        # 一致性条件 / Consistency: ν_pp E_⊥ = ν_perp E_|| (Maxwell-Betti reciprocity)
        # G_pp 默认按 sub-isotropic 估算（无独立实验值时） / Default G from sub-isotropic relation
        G_iso = E_pa / (2.0 * (1.0 + nu))  # 各向同性 G / Isotropic G
        self.G_pp_pa = G_iso * float(shear_ratio)  # 剪切模量 / Shear modulus
        center_clamp_radius_mm = float(config["project"].get("center_clamp_radius_mm", 8.0))  # 夹持半径 / Clamp radius
        self.clamp_indices = self._compute_clamp_indices(center_clamp_radius_mm, plate_length_mm)  # 夹持索引 / Clamp indices
        self.free_indices = torch.tensor([idx for idx in range(self.N * self.N) if idx not in self.clamp_indices], dtype=torch.long, device=self.device)  # 自由度 / Free DOFs
        self._build_difference_operators()  # 预构建差分算子 / Precompute difference operators
        self.base_accel = float(base_accel)  # 加速度 / Acceleration
        self.default_damping = float(default_damping)  # 阻尼 / Damping
        self.reference_frequency_hz = float(reference_frequency_hz)  # 参考频率 / Reference

    def _compute_clamp_indices(self, clamp_radius_mm: float, plate_length_mm: float) -> set[int]:  # 计算夹持 / Compute clamp
        clamp_radius_cells = (clamp_radius_mm / plate_length_mm) * float(self.N)  # 单元 / Cells
        center = (self.N - 1) / 2.0  # 中心 / Centre
        clamped: set[int] = set()  # 集合 / Set
        for row in range(self.N):  # 行 / Rows
            for col in range(self.N):  # 列 / Cols
                if (row - center) ** 2 + (col - center) ** 2 <= clamp_radius_cells ** 2:  # 圆内 / Inside
                    clamped.add(row * self.N + col)  # 加 / Add
        if not clamped:  # 默认中心 / Default centre
            clamped.add((self.N // 2) * self.N + (self.N // 2))  # 加 / Add
        return clamped  # 返回 / Return

    def _build_difference_operators(self) -> None:  # 构建 w_xx, w_yy, w_xy 差分算子 / Build w_xx, w_yy, w_xy operators
        N = self.N  # 网格 / Grid
        n = N * N  # DOF / DOFs
        inv_dx2 = 1.0 / (self.dx_m * self.dx_m)  # 1/dx² / 1/dx²
        inv_dy2 = 1.0 / (self.dy_m * self.dy_m)  # 1/dy² / 1/dy²
        inv_dxdy = 1.0 / (4.0 * self.dx_m * self.dy_m)  # 1/(4 dx dy) / 1/(4 dx dy)
        D_xx = torch.zeros((n, n), dtype=self.dtype, device=self.device)  # w_xx / w_xx
        D_yy = torch.zeros((n, n), dtype=self.dtype, device=self.device)  # w_yy / w_yy
        D_xy = torch.zeros((n, n), dtype=self.dtype, device=self.device)  # w_xy / w_xy

        def idx(r: int, c: int) -> int:  # 局部索引 / Local index
            return r * N + c  # 行列 / Row-col

        for r in range(N):  # 行 / Rows
            for c in range(N):  # 列 / Cols
                i = idx(r, c)  # 中心 / Centre
                # w_xx: (w[r, c+1] - 2 w[r,c] + w[r, c-1]) / dx²
                D_xx[i, i] += -2.0 * inv_dx2  # 中心 / Centre
                if c > 0:  # 左 / Left
                    D_xx[i, idx(r, c - 1)] += inv_dx2  # / coeff
                else:  # 边界用 ghost (反射) / Ghost (reflective)
                    D_xx[i, idx(r, c + 1)] += inv_dx2  # 镜像 / Mirror
                if c + 1 < N:  # 右 / Right
                    D_xx[i, idx(r, c + 1)] += inv_dx2  # / coeff
                else:  # 边界 / Boundary
                    D_xx[i, idx(r, c - 1)] += inv_dx2  # 镜像 / Mirror
                # w_yy: 行差分 / Row diff
                D_yy[i, i] += -2.0 * inv_dy2  # 中心 / Centre
                if r > 0:  # 上 / Up
                    D_yy[i, idx(r - 1, c)] += inv_dy2  # / coeff
                else:  # 边界 / Boundary
                    D_yy[i, idx(r + 1, c)] += inv_dy2  # 镜像 / Mirror
                if r + 1 < N:  # 下 / Down
                    D_yy[i, idx(r + 1, c)] += inv_dy2  # / coeff
                else:  # 边界 / Boundary
                    D_yy[i, idx(r - 1, c)] += inv_dy2  # 镜像 / Mirror
                # w_xy: 四角差 (w[r+1, c+1] - w[r+1, c-1] - w[r-1, c+1] + w[r-1, c-1]) / (4 dx dy)
                if r > 0 and c > 0:  # 左上 / Upper-left
                    D_xy[i, idx(r - 1, c - 1)] += inv_dxdy  # / coeff
                if r > 0 and c + 1 < N:  # 右上 / Upper-right
                    D_xy[i, idx(r - 1, c + 1)] += -inv_dxdy  # / coeff
                if r + 1 < N and c > 0:  # 左下 / Lower-left
                    D_xy[i, idx(r + 1, c - 1)] += -inv_dxdy  # / coeff
                if r + 1 < N and c + 1 < N:  # 右下 / Lower-right
                    D_xy[i, idx(r + 1, c + 1)] += inv_dxdy  # / coeff

        self.D_xx = D_xx  # 保存 / Store
        self.D_yy = D_yy  # 保存 / Store
        self.D_xy = D_xy  # 保存 / Store

    def upsample(self, H_design_mm: torch.Tensor) -> torch.Tensor:  # 升采样 / Upsample
        H = H_design_mm.to(dtype=self.dtype, device=self.device).unsqueeze(0).unsqueeze(0)  # 维度 / Dims
        upsampled = torch.nn.functional.interpolate(H, size=(self.N, self.N), mode="bilinear", align_corners=True)  # 双线性 / Bilinear
        return upsampled.squeeze(0).squeeze(0)  # 去维度 / Drop dims

    def compute_per_cell_stiffness(self, h_m: torch.Tensor, theta_rad: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:  # 计算 D11, D22, D12, D66, D16, D26 / Compute per-cell stiffness
        # 主轴常数 / Principal-axis constants
        h3 = h_m ** 3  # h³ / h³
        nu_pp = float(self.nu_pp)  # ν_|| / nu_||
        nu_pp_perp = nu_pp * (self.E_perp_pa / self.E_parallel_pa)  # 互易性 / Reciprocity
        denom = 1.0 - nu_pp * nu_pp_perp  # 公分母 / Denominator
        D11_p = self.E_parallel_pa * h3 / (12.0 * denom)  # 主 D11 / Principal D11
        D22_p = self.E_perp_pa * h3 / (12.0 * denom)  # 主 D22 / Principal D22
        D12_p = nu_pp_perp * D11_p  # 主 D12 / Principal D12
        D66_p = self.G_pp_pa * h3 / 12.0  # 主 D66 / Principal D66

        c = torch.cos(theta_rad)  # cos θ / cos θ
        s = torch.sin(theta_rad)  # sin θ / sin θ
        c2 = c * c  # c² / c²
        s2 = s * s  # s² / s²
        c4 = c2 * c2  # c⁴ / c⁴
        s4 = s2 * s2  # s⁴ / s⁴
        sc = s * c  # sc / sc

        # 4-th order tensor transformation in Voigt curvature notation / Reddy 2003 eq 1.3.94
        D11 = D11_p * c4 + 2.0 * (D12_p + 2.0 * D66_p) * s2 * c2 + D22_p * s4  # D11 / D11
        D22 = D11_p * s4 + 2.0 * (D12_p + 2.0 * D66_p) * s2 * c2 + D22_p * c4  # D22 / D22
        D12 = (D11_p + D22_p - 4.0 * D66_p) * s2 * c2 + D12_p * (c4 + s4)  # D12 / D12
        D66 = (D11_p + D22_p - 2.0 * D12_p) * s2 * c2 + D66_p * (c2 - s2) ** 2  # D66 / D66
        D16 = (D11_p - D12_p - 2.0 * D66_p) * sc * c2 - (D22_p - D12_p - 2.0 * D66_p) * sc * s2  # D16 / D16
        D26 = (D11_p - D12_p - 2.0 * D66_p) * sc * s2 - (D22_p - D12_p - 2.0 * D66_p) * sc * c2  # D26 / D26
        return D11, D22, D12, D66, D16, D26  # 返回 / Return

    def assemble_K_M(self, H_proxy_mm: torch.Tensor, theta_proxy_rad: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:  # 组装 K, M / Assemble K, M
        h_m = torch.clamp(H_proxy_mm * 1.0e-3, min=1.0e-6)  # 厚度 m / Thickness m
        D11, D22, D12, D66, D16, D26 = self.compute_per_cell_stiffness(h_m, theta_proxy_rad)  # 6 个分量 / 6 components
        node_mass = self.rho_kg_m3 * h_m * self.cell_area_m2  # 节点质量 / Nodal mass

        # 节点 D 系数（直接用同样的节点厚度/θ；严格做应在单元中心，但 25x25 网格上差别可忽略） / Nodal D coefs
        D11_f = D11.reshape(-1)  # 扁平 / Flat
        D22_f = D22.reshape(-1)  # / Flat
        D12_f = D12.reshape(-1)  # / Flat
        D66_f = D66.reshape(-1)  # / Flat
        D16_f = D16.reshape(-1)  # / Flat
        D26_f = D26.reshape(-1)  # / Flat

        # K = ∫ D κ^T κ dA — discretised as Σ_nodes [D L^T L] × cell_area (Galerkin) / Galerkin assembly
        # Bilinear form U = (1/2) (D11 w_xx² + D22 w_yy² + 2 D12 w_xx w_yy + 4 D66 w_xy² + 4 D16 w_xx w_xy + 4 D26 w_yy w_xy)
        Lxx = self.D_xx  # 差分 / Difference
        Lyy = self.D_yy  # 差分 / Difference
        Lxy = self.D_xy  # 差分 / Difference

        K = (Lxx.T @ (D11_f.unsqueeze(1) * Lxx) + Lyy.T @ (D22_f.unsqueeze(1) * Lyy) + 2.0 * Lxx.T @ (D12_f.unsqueeze(1) * Lyy) + 4.0 * Lxy.T @ (D66_f.unsqueeze(1) * Lxy) + 2.0 * Lxx.T @ (D16_f.unsqueeze(1) * Lxy) + 2.0 * Lxy.T @ (D16_f.unsqueeze(1) * Lxx) + 2.0 * Lyy.T @ (D26_f.unsqueeze(1) * Lxy) + 2.0 * Lxy.T @ (D26_f.unsqueeze(1) * Lyy)) * self.cell_area_m2  # 弯曲刚度 / Bending stiffness
        K = 0.5 * (K + K.T)  # 强制对称 / Enforce symmetry
        return K, node_mass.reshape(-1)  # 返回 / Return

    def _rayleigh_coefficients(self, damping_ratio: float, omega_ref: float) -> tuple[float, float]:  # Rayleigh / Rayleigh
        omega_ref = max(float(omega_ref), 1.0e-6)  # 限 / Clamp
        alpha = float(damping_ratio) * omega_ref  # α / α
        beta = float(damping_ratio) / omega_ref  # β / β
        return alpha, beta  # 返回 / Return

    def direct_forced_response(self, K_free: torch.Tensor, M_free: torch.Tensor, omega: torch.Tensor, damping_ratio: float) -> torch.Tensor:  # 强迫响应 / Forced response
        omega_ref = 2.0 * 3.141592653589793 * self.reference_frequency_hz  # 参考 / Ref
        alpha, beta = self._rayleigh_coefficients(float(damping_ratio), omega_ref)  # α β / α β
        force_free_real = -M_free * float(self.base_accel)  # 力 / Force
        force_free = force_free_real.to(self.cdtype)  # 复 / Complex
        K_c = K_free.to(self.cdtype)  # 复 / Complex
        M_c = M_free.to(self.cdtype)  # 复 / Complex
        omega_c = omega.to(self.cdtype)  # 复 / Complex
        A = K_c + 1j * omega_c * (alpha * torch.diag(M_c) + beta * K_c) - omega_c * omega_c * torch.diag(M_c)  # 复数矩阵 / Complex matrix
        u = torch.linalg.solve(A, force_free)  # 求解 / Solve
        return u  # 返回 / Return

    def expand_to_grid(self, u_free: torch.Tensor) -> torch.Tensor:  # 铺到完整网格 / Scatter
        full = torch.zeros(self.N * self.N, dtype=u_free.dtype, device=u_free.device)  # 零 / Zero
        full.index_copy_(0, self.free_indices, u_free)  # 写 / Write
        return full.reshape(self.N, self.N)  # 二维 / 2D

    def amplitude_at_frequency(self, H_design_mm: torch.Tensor, theta_design_rad: torch.Tensor, frequency_hz: torch.Tensor, damping_ratio: float | None = None) -> torch.Tensor:  # 单频振幅 / Single-freq amplitude
        H_proxy = self.upsample(H_design_mm)  # 升采样 H / Upsample H
        theta_proxy = self.upsample(theta_design_rad)  # 升采样 θ / Upsample θ
        K, M = self.assemble_K_M(H_proxy, theta_proxy)  # 组装 / Assemble
        free = self.free_indices  # 自由 / Free
        K_free = K.index_select(0, free).index_select(1, free)  # 自由刚度 / Free stiffness
        M_free = M.index_select(0, free)  # 自由质量 / Free mass
        omega = 2.0 * 3.141592653589793 * frequency_hz  # 角频率 / Omega
        damp = float(damping_ratio if damping_ratio is not None else self.default_damping)  # 阻尼 / Damping
        u_free = self.direct_forced_response(K_free, M_free, omega, damp)  # 求解 / Solve
        u_grid = self.expand_to_grid(u_free)  # 铺 / Scatter
        return torch.abs(u_grid)  # 振幅 / Amplitude
