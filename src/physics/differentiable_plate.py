from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator

import torch  # 导入张量计算库 / Import tensor computation library


@dataclass  # 数据类装饰器 / Dataclass decorator
class PlateForwardResult:  # 板模型前向结果数据类 / Plate-model forward result data class
    response_complex: torch.Tensor  # 复数响应 (N, N) / Complex response (N, N)
    amplitude: torch.Tensor  # 归一化振幅 (N, N) / Normalised amplitude (N, N)
    natural_frequencies_hz: torch.Tensor | None  # 自然频率 Hz (可选) / Natural frequencies in Hz (optional)


class DifferentiablePlate:  # 可微 KL 板模型 / Differentiable KL plate model
    def __init__(self, config: dict, proxy_grid_size: int = 25, base_accel: float = 1.0, default_damping: float = 0.02, reference_frequency_hz: float = 600.0, dtype: torch.dtype = torch.float64, device: str | torch.device = "cpu") -> None:  # 初始化板模型 / Initialise plate model
        self.config = config  # 保存配置 / Store config
        self.N = int(proxy_grid_size)  # 代理网格分辨率 / Proxy grid resolution
        if self.N % 2 == 0:  # 强制奇数以对齐中心格 / Force odd to align centre cell
            self.N += 1  # 自增一格 / Increment by one
        self.dtype = dtype  # 浮点精度 / Float precision
        self.cdtype = torch.complex128 if dtype == torch.float64 else torch.complex64  # 复数精度匹配实数 / Complex precision matching real
        self.device = torch.device(device)  # 运算设备 / Compute device
        plate_length_mm = float(config["project"]["plate_length_mm"])  # 读取板长度 / Read plate length
        plate_width_mm = float(config["project"]["plate_width_mm"])  # 读取板宽度 / Read plate width
        self.plate_length_mm = plate_length_mm  # 保存板长度 / Store plate length
        self.dx_m = plate_length_mm * 1.0e-3 / float(self.N)  # 计算 x 方向单元尺寸 / Compute x cell size
        self.dy_m = plate_width_mm * 1.0e-3 / float(self.N)  # 计算 y 方向单元尺寸 / Compute y cell size
        self.cell_area_m2 = self.dx_m * self.dy_m  # 计算单元面积 / Compute cell area
        material = config.get("material", {})  # 读取材料字典 / Read material dict
        self.E_pa = float(material.get("youngs_modulus_pa", 2.0e9))  # 杨氏模量 / Young's modulus
        self.nu = float(material.get("poisson_ratio", 0.35))  # 泊松比 / Poisson ratio
        self.rho_kg_m3 = float(material.get("density_kg_m3", 1200.0))  # 密度 / Density
        center_clamp_radius_mm = float(config["project"].get("center_clamp_radius_mm", 8.0))  # 中心夹持半径 / Centre clamp radius
        self.clamp_indices = self._compute_clamp_indices(center_clamp_radius_mm, plate_length_mm)  # 计算夹持索引 / Compute clamp indices
        self.free_indices = torch.tensor([idx for idx in range(self.N * self.N) if idx not in self.clamp_indices], dtype=torch.long, device=self.device)  # 自由度索引 / Free DOF indices
        self.L_matrix = self._build_laplacian()  # 预构建拉普拉斯 / Precompute Laplacian
        self.base_accel = float(base_accel)  # 基础激振加速度 / Base-excitation acceleration
        self.default_damping = float(default_damping)  # 默认模态阻尼比 / Default modal damping
        self.reference_frequency_hz = float(reference_frequency_hz)  # Rayleigh 标定参考频率 / Rayleigh calibration reference frequency

    def _compute_clamp_indices(self, clamp_radius_mm: float, plate_length_mm: float) -> set[int]:  # 计算夹持自由度 / Compute clamped DOF indices
        clamp_radius_cells = (clamp_radius_mm / plate_length_mm) * float(self.N)  # 夹持半径换算成格 / Convert clamp radius to cells
        center = (self.N - 1) / 2.0  # 中心坐标 / Centre coordinate
        clamped: set[int] = set()  # 创建夹持集合 / Create clamped set
        for row in range(self.N):  # 遍历行 / Iterate rows
            for col in range(self.N):  # 遍历列 / Iterate columns
                if (row - center) ** 2 + (col - center) ** 2 <= clamp_radius_cells ** 2:  # 落在夹持圆内 / Within clamp circle
                    clamped.add(row * self.N + col)  # 加入夹持集合 / Add to clamped set
        if not clamped:  # 至少夹住中心一格 / Clamp at least the centre cell
            clamped.add((self.N // 2) * self.N + (self.N // 2))  # 添加中心格 / Add centre cell
        return clamped  # 返回夹持索引 / Return clamped indices

    def _build_laplacian(self) -> torch.Tensor:  # 构建五点拉普拉斯 / Build five-point Laplacian
        N = self.N  # 读取网格分辨率 / Read grid resolution
        n = N * N  # 自由度数 / DOF count
        rows: list[int] = []  # 创建行索引 / Create row indices
        cols: list[int] = []  # 创建列索引 / Create column indices
        vals: list[float] = []  # 创建数值列表 / Create value list
        inv_dx2 = 1.0 / (self.dx_m * self.dx_m)  # x 方向反平方 / Inverse x squared
        inv_dy2 = 1.0 / (self.dy_m * self.dy_m)  # y 方向反平方 / Inverse y squared
        for r in range(N):  # 遍历行 / Iterate rows
            for c in range(N):  # 遍历列 / Iterate columns
                i = r * N + c  # 计算扁平索引 / Compute flat index
                rows.append(i); cols.append(i); vals.append(-2.0 * inv_dx2 - 2.0 * inv_dy2)  # 中心系数 / Centre coefficient
                if r > 0:  # 上邻居 / Upper neighbour
                    rows.append(i); cols.append((r - 1) * N + c); vals.append(inv_dy2)  # 上邻系数 / Upper coefficient
                if r + 1 < N:  # 下邻居 / Lower neighbour
                    rows.append(i); cols.append((r + 1) * N + c); vals.append(inv_dy2)  # 下邻系数 / Lower coefficient
                if c > 0:  # 左邻居 / Left neighbour
                    rows.append(i); cols.append(r * N + (c - 1)); vals.append(inv_dx2)  # 左邻系数 / Left coefficient
                if c + 1 < N:  # 右邻居 / Right neighbour
                    rows.append(i); cols.append(r * N + (c + 1)); vals.append(inv_dx2)  # 右邻系数 / Right coefficient
        L = torch.zeros((n, n), dtype=self.dtype, device=self.device)  # 创建稠密 Laplacian / Create dense Laplacian
        L[torch.tensor(rows, dtype=torch.long, device=self.device), torch.tensor(cols, dtype=torch.long, device=self.device)] = torch.tensor(vals, dtype=self.dtype, device=self.device)  # 写入非零项 / Scatter nonzero entries
        return L  # 返回 Laplacian / Return Laplacian

    def upsample(self, H_design_mm: torch.Tensor) -> torch.Tensor:  # 升采样设计厚度到代理网格 / Upsample design thickness to proxy grid
        H = H_design_mm.to(dtype=self.dtype, device=self.device).unsqueeze(0).unsqueeze(0)  # 增加 N C 维度 / Add N and C dims
        upsampled = torch.nn.functional.interpolate(H, size=(self.N, self.N), mode="bilinear", align_corners=True)  # 双线性升采样 / Bilinear upsample
        return upsampled.squeeze(0).squeeze(0)  # 去除 N C 维度 / Drop N and C dims

    def assemble_K_M(self, H_proxy_mm: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:  # 组装刚度与质量 / Assemble stiffness and mass
        h_m = torch.clamp(H_proxy_mm * 1.0e-3, min=1.0e-6)  # 厚度转米并限下界 / Convert to metres with floor
        D = self.E_pa * h_m ** 3 / (12.0 * (1.0 - self.nu ** 2))  # 弯曲刚度 / Bending stiffness
        node_mass = self.rho_kg_m3 * h_m * self.cell_area_m2  # 节点质量 / Nodal mass
        D_flat = D.reshape(-1)  # 扁平刚度 / Flat stiffness
        K = self.L_matrix.T @ (D_flat.unsqueeze(1) * self.L_matrix) * self.cell_area_m2  # 双调和刚度 / Biharmonic stiffness
        K = 0.5 * (K + K.T)  # 强制对称 / Enforce symmetry
        return K, node_mass.reshape(-1)  # 返回刚度与对角质量 / Return stiffness and diagonal mass

    def _rayleigh_coefficients(self, damping_ratio: float, omega_ref: float) -> tuple[float, float]:  # 计算 Rayleigh 阻尼系数 / Compute Rayleigh damping coefficients
        omega_ref = max(float(omega_ref), 1.0e-6)  # 限制参考角频率 / Clamp reference angular frequency
        alpha = float(damping_ratio) * omega_ref  # 质量阻尼系数 / Mass damping coefficient
        beta = float(damping_ratio) / omega_ref  # 刚度阻尼系数 / Stiffness damping coefficient
        return alpha, beta  # 返回 Rayleigh 系数 / Return Rayleigh coefficients

    def direct_forced_response(self, K_free: torch.Tensor, M_free: torch.Tensor, omega: torch.Tensor, damping_ratio: float) -> torch.Tensor:  # 直接复数频域求解 / Direct complex frequency-domain solve
        omega_ref = 2.0 * 3.141592653589793 * self.reference_frequency_hz  # 参考角频率 / Reference angular frequency
        alpha, beta = self._rayleigh_coefficients(float(damping_ratio), omega_ref)  # 计算 Rayleigh 系数 / Compute Rayleigh coefficients
        force_free_real = -M_free * float(self.base_accel)  # 基础激振力 / Base-excitation force
        force_free = force_free_real.to(self.cdtype)  # 转复数 / Cast to complex
        K_c = K_free.to(self.cdtype)  # 刚度转复数 / Cast stiffness to complex
        M_c = M_free.to(self.cdtype)  # 质量转复数 / Cast mass to complex
        omega_c = omega.to(self.cdtype)  # 角频率转复数 / Cast omega to complex
        damping_term = (alpha * M_c).unsqueeze(0) * torch.eye(M_c.shape[0], dtype=self.cdtype, device=self.device)  # 质量阻尼对角 / Mass-damping diagonal
        A = K_c + 1j * omega_c * (alpha * torch.diag(M_c) + beta * K_c) - omega_c * omega_c * torch.diag(M_c)  # 复数系数矩阵 / Complex coefficient matrix
        del damping_term  # 释放无用变量 / Drop unused variable
        u = torch.linalg.solve(A, force_free)  # 直接复数求解 / Direct complex solve
        return u  # 返回复数响应 / Return complex response

    def expand_to_grid(self, u_free: torch.Tensor) -> torch.Tensor:  # 把自由度响应铺到完整网格 / Scatter free-DOF response to full grid
        full = torch.zeros(self.N * self.N, dtype=u_free.dtype, device=u_free.device)  # 创建零向量 / Create zero vector
        full.index_copy_(0, self.free_indices, u_free)  # 写入自由度响应 / Write free-DOF response
        return full.reshape(self.N, self.N)  # 返回二维响应 / Return 2-D response

    def forward(self, H_design_mm: torch.Tensor, drive_frequency_hz: float | torch.Tensor, damping_ratio: float | None = None, return_natural_freqs: bool = False) -> PlateForwardResult:  # 端到端前向 / End-to-end forward pass
        damping = float(damping_ratio) if damping_ratio is not None else self.default_damping  # 决定阻尼比 / Resolve damping ratio
        if isinstance(drive_frequency_hz, torch.Tensor):  # 传入张量频率 / Tensor drive frequency
            omega = 2.0 * 3.141592653589793 * drive_frequency_hz.to(dtype=self.dtype, device=self.device)  # 角频率张量 / Angular-frequency tensor
        else:  # 传入标量频率 / Scalar drive frequency
            omega = torch.tensor(2.0 * 3.141592653589793 * float(drive_frequency_hz), dtype=self.dtype, device=self.device)  # 角频率标量张量 / Scalar angular-frequency tensor
        H_proxy = self.upsample(H_design_mm)  # 升采样厚度 / Upsample thickness
        K, M_diag = self.assemble_K_M(H_proxy)  # 组装 K 与 M / Assemble K and M
        free = self.free_indices  # 自由度索引 / Free indices
        K_free = K.index_select(0, free).index_select(1, free)  # 截取自由刚度 / Slice free stiffness
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-12)  # 截取自由质量并限下界 / Slice free mass with floor
        u_free = self.direct_forced_response(K_free, M_free, omega, damping)  # 直接频域求解 / Direct frequency-domain solve
        response_complex = self.expand_to_grid(u_free)  # 铺回网格 / Scatter to grid
        amplitude = torch.abs(response_complex)  # 计算振幅 / Compute amplitude
        amplitude = amplitude / (torch.amax(amplitude) + 1.0e-12)  # 归一化振幅 / Normalise amplitude
        natural_freqs: torch.Tensor | None = None  # 默认不计算自然频率 / No natural frequencies by default
        if return_natural_freqs:  # 仅在请求时计算 / Compute only on request
            with torch.no_grad():  # 自然频率仅用于诊断不参与梯度 / Natural frequencies are diagnostic only
                inv_sqrt_M = 1.0 / torch.sqrt(M_free)  # 质量平方根反 / Inverse mass square root
                K_scaled = K_free.detach() * inv_sqrt_M.unsqueeze(0) * inv_sqrt_M.unsqueeze(1)  # 标准化刚度 / Symmetric standard problem
                K_scaled = 0.5 * (K_scaled + K_scaled.T)  # 强制对称 / Force symmetry
                eigvals = torch.linalg.eigvalsh(K_scaled)  # 求实数本征值 / Solve real eigenvalues
                natural_freqs = torch.sqrt(torch.clamp(eigvals, min=0.0)) / (2.0 * 3.141592653589793)  # 转 Hz / Convert to Hz
        return PlateForwardResult(response_complex=response_complex, amplitude=amplitude, natural_frequencies_hz=natural_freqs)  # 返回结果 / Return result
