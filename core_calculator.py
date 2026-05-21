# core_calculator.py
"""
杀虫剂配药计算器 - 核心算法模块

本模块实现了杀虫剂配药作业中的专业计算逻辑，包括：
1. 多维度单位换算体系（流量、长度、速度、体积、时间）
2. 空间参数自动联动换算（体积↔面积通过雾层高度桥接）
3. 双模式求解引擎（已知步速/已知稀释倍数）
4. 室内场景业务规则（禁用步速计算）
5. 有效成分与制剂用药量的专业换算

设计思路：
- 采用"标准化中间层"策略：所有输入参数先转换为标准单位（ml, m, s, m³），
  计算完成后再按用户偏好单位输出，避免单位混乱导致的计算错误。
- 空间参数四选一设计：用户只需提供一种空间描述（室内/室外 × 体积/面积），
  系统自动通过雾层高度完成体积-面积换算，降低操作复杂度。
- 双分支求解：根据用户已知条件（步速或稀释倍数）自动选择求解路径，
  覆盖室外喷雾作业和室内滞留喷洒两种典型场景。
"""

# ==================== 常量定义 ====================

# 标准单位体系
STD_FLOW_UNIT = "ml/s"  # 流量标准单位
STD_LENGTH_UNIT = "m"  # 长度标准单位
STD_SPEED_UNIT = "m/s"  # 速度标准单位
STD_VOLUME_UNIT = "m³"  # 体积标准单位
STD_TIME_UNIT = "s"  # 时间标准单位
STD_DOSAGE_VOL = "ml/m³"  # 体积法用药量标准单位
STD_DOSAGE_AREA = "ml/m²"  # 面积法用药量标准单位

# 有效成分换算常数
ACTIVE_INGREDIENT_FACTOR = 10  # mg → ml 转换系数 (÷含量%÷10)


# ==================== 单位换算模块 ====================

def convert_flow(value: float, unit: str) -> float:
    """
    流量单位换算至标准单位 ml/s

    支持单位：ml/s, ml/min, L/min, L/h
    换算关系：1 L = 1000 ml, 1 min = 60 s, 1 h = 3600 s

    Args:
        value: 流量数值
        unit: 原始单位字符串

    Returns:
        float: 标准单位 ml/s 下的数值

    Raises:
        ValueError: 不支持的单位类型
    """
    if unit == "ml/s":
        return value
    elif unit == "ml/min":
        return value * 1.0 / 60.0
    elif unit == "L/min":
        return value * 1000.0 / 60.0
    elif unit == "L/h":
        return value * 1000.0 / 3600.0
    else:
        raise ValueError(f"不支持的流量单位: {unit}")


def convert_length(value: float, unit: str) -> float:
    """
    长度单位换算至标准单位 m

    支持单位：m, cm, mm
    换算关系：1 m = 100 cm = 1000 mm

    Args:
        value: 长度数值
        unit: 原始单位字符串

    Returns:
        float: 标准单位 m 下的数值

    Raises:
        ValueError: 不支持的长度单位
    """
    if unit == "m":
        return value
    elif unit == "cm":
        return value / 100.0
    elif unit == "mm":
        return value / 1000.0
    else:
        raise ValueError(f"不支持的长度单位: {unit}")


def convert_speed(value: float, unit: str) -> float:
    """
    速度单位换算至标准单位 m/s

    支持单位：m/s, m/min, km/h
    换算关系：1 min = 60 s, 1 km = 1000 m, 1 h = 3600 s

    Args:
        value: 速度数值
        unit: 原始单位字符串

    Returns:
        float: 标准单位 m/s 下的数值

    Raises:
        ValueError: 不支持的速度单位
    """
    if unit == "m/s":
        return value
    elif unit == "m/min":
        return value / 60.0
    elif unit == "km/h":
        return value * 1000.0 / 3600.0
    else:
        raise ValueError(f"不支持的速度单位: {unit}")


def reverse_flow(value: float, unit: str) -> float:
    """流量反向换算：从标准单位 ml/s 转回用户偏好单位"""
    if unit == "ml/s":
        return value
    elif unit == "L/min":
        return value * 60.0 / 1000.0
    elif unit == "L/h":
        return value * 3600.0 / 1000.0
    else:
        raise ValueError(f"不支持的流量单位: {unit}")


def reverse_speed(value: float, unit: str) -> float:
    """速度反向换算：从标准单位 m/s 转回用户偏好单位"""
    if unit == "m/s":
        return value
    elif unit == "m/min":
        return value * 60.0
    elif unit == "km/h":
        return value * 3.6
    else:
        raise ValueError(f"不支持的速度单位: {unit}")


def reverse_time(value: float, unit: str) -> float:
    """时间反向换算：从标准单位 s 转回用户偏好单位"""
    if unit == "s":
        return value
    elif unit == "min":
        return value / 60.0
    elif unit == "h":
        return value / 3600.0
    else:
        raise ValueError(f"不支持的时间单位: {unit}")


def reverse_volume(value: float, unit: str) -> float:
    """体积反向换算：从标准单位 ml 转回用户偏好单位"""
    if unit == "ml":
        return value
    elif unit == "L":
        return value / 1000.0
    else:
        raise ValueError(f"不支持的体积单位: {unit}")


# ==================== 空间参数联动换算模块 ====================

class SpaceParameter:
    """
    空间参数封装类

    实现四选一空间参数的自动联动换算：
    - 用户输入：室内空间/室内面积/室外空间/室外面积 任选其一
    - 内部维护：同时保存体积(m³)和面积(m²)两种表达
    - 换算桥梁：雾层高度(m)

    业务规则：
    1. 体积法计算（用药量单位 ml/m³）需要空间体积
    2. 面积法计算（用药量单位 ml/m²）需要平面面积
    3. 当用户提供的参数类型与计算模式不匹配时，自动通过雾层高度换算
    """

    def __init__(self, space_type: str, raw_value: float, fog_height: float):
        """
        初始化空间参数

        Args:
            space_type: 空间类型标识
                       "indoor_vol"/"indoor_area"/"outdoor_vol"/"outdoor_area"
            raw_value: 用户输入的原始数值
            fog_height: 雾层高度（标准单位 m），作为体积-面积换算的桥梁

        Raises:
            ValueError: 参数不合法
        """
        if raw_value <= 0:
            raise ValueError("空间参数数值必须大于0")
        if fog_height <= 0:
            raise ValueError("雾层高度必须大于0，用于体积-面积换算")

        self.space_type = space_type
        self.raw_value = raw_value
        self.fog_height = fog_height

        # 解析空间类型
        self.is_indoor = "indoor" in space_type
        self.is_outdoor = "outdoor" in space_type
        self.is_volume_input = "_vol" in space_type
        self.is_area_input = "_area" in space_type

        # 自动联动换算
        if self.is_volume_input:
            self.volume = raw_value  # 用户直接提供体积
            self.area = raw_value / fog_height  # 自动换算面积 = 体积 ÷ 雾层高度
        else:
            self.area = raw_value  # 用户直接提供面积
            self.volume = raw_value * fog_height  # 自动换算体积 = 面积 × 雾层高度

    def get_label(self) -> tuple:
        """
        获取当前空间的文字标签

        Returns:
            tuple: (体积标签, 面积标签, 体积数值, 面积数值)
        """
        if self.is_outdoor:
            return ("室外空间", "室外面积", self.volume, self.area)
        else:
            return ("室内空间", "室内面积", self.volume, self.area)

    def get_conversion_note(self, target_mode: str) -> str:
        """
        生成换算说明文本，用于展示计算过程

        Args:
            target_mode: 目标计算模式，"volume" 或 "area"

        Returns:
            str: 换算说明字符串，无换算时返回空字符串
        """
        if self.is_volume_input and target_mode == "area":
            return (
                f"【空间自动换算】\n"
                f"用户输入体积参数 {self.raw_value:.1f} m³，"
                f"目标计算需要面积参数\n"
                f"自动换算：面积 = 体积 ÷ 雾层高度 = "
                f"{self.raw_value:.1f} ÷ {self.fog_height:.2f} = {self.area:.1f} m²"
            )
        elif self.is_area_input and target_mode == "volume":
            return (
                f"【空间自动换算】\n"
                f"用户输入面积参数 {self.raw_value:.1f} m²，"
                f"目标计算需要体积参数\n"
                f"自动换算：体积 = 面积 × 雾层高度 = "
                f"{self.raw_value:.1f} × {self.fog_height:.2f} = {self.volume:.1f} m³"
            )
        return ""


# ==================== 药剂参数处理模块 ====================

class ChemicalParameter:
    """
    药剂参数封装类

    支持两种用药量输入模式：
    1. 制剂用药量：直接输入 ml/m³ 或 ml/m²
    2. 有效成分用药量：输入 mg/m³ + 有效成分含量(%)，自动换算为制剂用药量

    换算公式（行业通用）：
        制剂用药量(ml/m³) = 有效成分用药量(mg/m³) ÷ 含量(%) ÷ 10
    """

    def __init__(self, chem_type: str, dosage_value: float = None,
                 active_dosage: float = None, active_conc: float = None):
        """
        初始化药剂参数

        Args:
            chem_type: "formulation"(制剂) 或 "active"(有效成分)
            dosage_value: 制剂用药量数值（chem_type="formulation"时使用）
            active_dosage: 有效成分用药量 mg/m³（chem_type="active"时使用）
            active_conc: 有效成分含量 %（chem_type="active"时使用）

        Raises:
            ValueError: 参数不合法或换算失败
        """
        self.chem_type = chem_type

        if chem_type == "active":
            if active_conc is None or active_conc <= 0:
                raise ValueError("总有效成分含量必须大于0")
            if active_dosage is None or active_dosage < 0:
                raise ValueError("有效成分用药量不能为负")

            self.active_dosage = active_dosage
            self.active_conc = active_conc
            # 行业换算公式：mg → ml 转换
            self.dosage = active_dosage / active_conc / ACTIVE_INGREDIENT_FACTOR
            self.dosage_unit = "ml/m³"  # 有效成分模式锁定为体积法
            self.conversion_note = (
                f"【有效成分换算】\n"
                f"制剂用药量 = 有效成分用药量 ÷ 含量 ÷ 10\n"
                f"= {active_dosage:.1f} mg/m³ ÷ {active_conc:.1f}% ÷ 10\n"
                f"= {self.dosage:.4f} ml/m³"
            )
        else:
            if dosage_value is None or dosage_value < 0:
                raise ValueError("制剂用药量不能为负")

            self.dosage = dosage_value
            self.dosage_unit = None  # 由外部指定 ml/m³ 或 ml/m²
            self.conversion_note = ""
            self.active_dosage = None
            self.active_conc = None


# ==================== 求解引擎模块 ====================

class CalculationResult:
    """
    计算结果封装类

    统一封装所有计算结果，支持单位反向转换
    """

    def __init__(self):
        self.total_spray = None  # 总喷药量 (ml)
        self.stock_solution = None  # 原液用药量 (ml)
        self.dilution_ratio = None  # 稀释倍数
        self.walking_speed = None  # 步速 (m/s)
        self.spray_duration = None  # 喷雾时长 (s)
        self.calculation_detail = ""  # 详细计算过程文本
        self.mode_description = ""  # 计算模式描述


def solve_by_speed(flow_rate: float, swath_width: float, fog_height: float,
                   space: SpaceParameter, chemical: ChemicalParameter,
                   speed_ms: float, dosage_unit: str) -> CalculationResult:
    """
    已知步速求解引擎

    根据已知步速，求解稀释倍数、总喷药量、原液用药量、喷雾时长。
    适用于室外喷雾作业场景。

    核心公式体系：
    - 稀释倍数(体积法) = 流量 ÷ (喷幅 × 雾层高度 × 步速 × 用药量)
    - 稀释倍数(面积法) = 流量 ÷ (喷幅 × 步速 × 用药量)
    - 总喷药量 = 用药量 × 空间 × 稀释倍数（验算用）
    - 总喷药量(步速法) = 流量 × 空间 ÷ (喷幅 × 雾层高度 × 步速) [体积法]
    - 总喷药量(步速法) = 流量 × 面积 ÷ (喷幅 × 步速) [面积法]
    - 原液用药量 = 用药量 × 空间(或面积)
    - 喷雾时长 = 总喷药量 ÷ 流量

    Args:
        flow_rate: 喷雾机流量 (ml/s，标准单位)
        swath_width: 喷幅 (m，标准单位)
        fog_height: 雾层高度 (m，标准单位)
        space: SpaceParameter 空间参数对象
        chemical: ChemicalParameter 药剂参数对象
        speed_ms: 步速 (m/s，标准单位)
        dosage_unit: 用药量单位，"ml/m³" 或 "ml/m²"

    Returns:
        CalculationResult: 完整计算结果
    """
    result = CalculationResult()
    Q, W, H = flow_rate, swath_width, fog_height
    D = chemical.dosage
    v = speed_ms
    label_vol, label_area, vol, area = space.get_label()

    # 确定计算模式
    is_volume_mode = (dosage_unit == "ml/m³")

    if is_volume_mode:
        # 体积法计算分支
        d = Q / (W * H * v * D)
        total = Q * vol / (H * W * v)
        stock = D * vol

        result.dilution_ratio = d
        result.total_spray = total
        result.stock_solution = stock
        result.walking_speed = v

        # 构建详细计算过程
        convert_note = space.get_conversion_note("volume")
        detail = f"""
【求解模式】已知步速 → 求稀释倍数、总喷药量、原液用药量、喷雾时长

{convert_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标准参数：
  流量 Q      = {Q:.4f} ml/s
  喷幅 W      = {W:.2f} m
  雾层高度 H  = {H:.2f} m
  {label_vol} V = {vol:.1f} m³
  用药量 D    = {D:.4f} ml/m³
  步速 v      = {v:.4f} m/s

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
计算过程：

① 稀释倍数 = Q ÷ (W × H × v × D)
           = {Q:.4f} ÷ ({W:.2f} × {H:.2f} × {v:.4f} × {D:.4f})
           = {d:.2f} 倍

② 总喷药量 = Q × V ÷ (H × W × v)
           = {Q:.4f} × {vol:.1f} ÷ ({H:.2f} × {W:.2f} × {v:.4f})
           = {total:.2f} ml
   （验算：D × V × d = {D:.4f} × {vol:.1f} × {d:.2f} = {D * vol * d:.2f} ml）

③ 原液用药量 = D × V
             = {D:.4f} × {vol:.1f}
             = {stock:.2f} ml

④ 喷雾时长 = 总喷药量 ÷ Q
           = {total:.2f} ÷ {Q:.4f}
           = {total / Q:.2f} s
"""
    else:
        # 面积法计算分支
        d = Q / (W * v * D)
        total = Q * area / (W * v)
        stock = D * area

        result.dilution_ratio = d
        result.total_spray = total
        result.stock_solution = stock
        result.walking_speed = v

        convert_note = space.get_conversion_note("area")
        detail = f"""
【求解模式】已知步速 → 求稀释倍数、总喷药量、原液用药量、喷雾时长

{convert_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标准参数：
  流量 Q      = {Q:.4f} ml/s
  喷幅 W      = {W:.2f} m
  {label_area} A = {area:.1f} m²
  用药量 D    = {D:.4f} ml/m²
  步速 v      = {v:.4f} m/s

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
计算过程：

① 稀释倍数 = Q ÷ (W × v × D)
           = {Q:.4f} ÷ ({W:.2f} × {v:.4f} × {D:.4f})
           = {d:.2f} 倍

② 总喷药量 = Q × A ÷ (W × v)
           = {Q:.4f} × {area:.1f} ÷ ({W:.2f} × {v:.4f})
           = {total:.2f} ml
   （验算：D × A × d = {D:.4f} × {area:.1f} × {d:.2f} = {D * area * d:.2f} ml）

③ 原液用药量 = D × A
             = {D:.4f} × {area:.1f}
             = {stock:.2f} ml

④ 喷雾时长 = 总喷药量 ÷ Q
           = {total:.2f} ÷ {Q:.4f}
           = {total / Q:.2f} s
"""

    result.spray_duration = total / Q
    result.calculation_detail = detail
    result.mode_description = "已知步速求解模式"
    return result


def solve_by_dilution(flow_rate: float, swath_width: float, fog_height: float,
                      space: SpaceParameter, chemical: ChemicalParameter,
                      dilution: float, dosage_unit: str,
                      is_indoor: bool) -> CalculationResult:
    """
    已知稀释倍数求解引擎

    根据已知稀释倍数，求解步速（室外）、总喷药量、原液用药量、喷雾时长。
    适用于室内滞留喷洒和室外喷雾作业两种场景。

    核心公式体系：
    - 步速(体积法) = 流量 ÷ (喷幅 × 雾层高度 × 稀释倍数 × 用药量)
    - 步速(面积法) = 流量 ÷ (喷幅 × 稀释倍数 × 用药量)
    - 总喷药量 = 用药量 × 空间 × 稀释倍数
    - 原液用药量 = 用药量 × 空间(或面积)
    - 喷雾时长 = 总喷药量 ÷ 流量

    室内场景特殊规则：不计算步速，仅计算总喷药量、原液用药量、喷雾时长。

    Args:
        flow_rate: 喷雾机流量 (ml/s，标准单位)
        swath_width: 喷幅 (m，标准单位)
        fog_height: 雾层高度 (m，标准单位)
        space: SpaceParameter 空间参数对象
        chemical: ChemicalParameter 药剂参数对象
        dilution: 稀释倍数
        dosage_unit: 用药量单位，"ml/m³" 或 "ml/m²"
        is_indoor: 是否为室内场景（True时不计算步速）

    Returns:
        CalculationResult: 完整计算结果
    """
    result = CalculationResult()
    Q, W, H = flow_rate, swath_width, fog_height
    D = chemical.dosage
    d = dilution
    label_vol, label_area, vol, area = space.get_label()

    is_volume_mode = (dosage_unit == "ml/m³")
    v = None  # 步速，室内场景为 None

    if is_volume_mode:
        # 体积法计算分支
        if not is_indoor:
            v = Q / (W * H * d * D)

        total = D * vol * d
        stock = D * vol

        result.dilution_ratio = d
        result.total_spray = total
        result.stock_solution = stock
        result.walking_speed = v

        convert_note = space.get_conversion_note("volume")

        if is_indoor:
            detail = f"""
【求解模式】已知稀释倍数（室内场景）→ 求总喷药量、原液用药量、喷雾时长

{convert_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标准参数：
  流量 Q      = {Q:.4f} ml/s
  喷幅 W      = {W:.2f} m
  雾层高度 H  = {H:.2f} m
  {label_vol} V = {vol:.1f} m³
  用药量 D    = {D:.4f} ml/m³
  稀释倍数 d  = {d:.1f} 倍

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
计算过程：

① 总喷药量 = D × V × d
           = {D:.4f} × {vol:.1f} × {d:.1f}
           = {total:.2f} ml

② 原液用药量 = D × V
             = {D:.4f} × {vol:.1f}
             = {stock:.2f} ml

③ 喷雾时长 = 总喷药量 ÷ Q
           = {total:.2f} ÷ {Q:.4f}
           = {total / Q:.2f} s

注：室内场景不计算步速。
"""
        else:
            detail = f"""
【求解模式】已知稀释倍数 → 求步速、总喷药量、原液用药量、喷雾时长

{convert_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标准参数：
  流量 Q      = {Q:.4f} ml/s
  喷幅 W      = {W:.2f} m
  雾层高度 H  = {H:.2f} m
  {label_vol} V = {vol:.1f} m³
  用药量 D    = {D:.4f} ml/m³
  稀释倍数 d  = {d:.1f} 倍

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
计算过程：

① 步速 = Q ÷ (W × H × d × D)
       = {Q:.4f} ÷ ({W:.2f} × {H:.2f} × {d:.1f} × {D:.4f})
       = {v:.4f} m/s

② 总喷药量 = D × V × d
           = {D:.4f} × {vol:.1f} × {d:.1f}
           = {total:.2f} ml

③ 原液用药量 = D × V
             = {D:.4f} × {vol:.1f}
             = {stock:.2f} ml

④ 喷雾时长 = 总喷药量 ÷ Q
           = {total:.2f} ÷ {Q:.4f}
           = {total / Q:.2f} s
"""
    else:
        # 面积法计算分支
        if not is_indoor:
            v = Q / (W * d * D)

        total = D * area * d
        stock = D * area

        result.dilution_ratio = d
        result.total_spray = total
        result.stock_solution = stock
        result.walking_speed = v

        convert_note = space.get_conversion_note("area")

        if is_indoor:
            detail = f"""
【求解模式】已知稀释倍数（室内场景）→ 求总喷药量、原液用药量、喷雾时长

{convert_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标准参数：
  流量 Q      = {Q:.4f} ml/s
  喷幅 W      = {W:.2f} m
  {label_area} A = {area:.1f} m²
  用药量 D    = {D:.4f} ml/m²
  稀释倍数 d  = {d:.1f} 倍

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
计算过程：

① 总喷药量 = D × A × d
           = {D:.4f} × {area:.1f} × {d:.1f}
           = {total:.2f} ml

② 原液用药量 = D × A
             = {D:.4f} × {area:.1f}
             = {stock:.2f} ml

③ 喷雾时长 = 总喷药量 ÷ Q
           = {total:.2f} ÷ {Q:.4f}
           = {total / Q:.2f} s

注：室内场景不计算步速。
"""
        else:
            detail = f"""
【求解模式】已知稀释倍数 → 求步速、总喷药量、原液用药量、喷雾时长

{convert_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
标准参数：
  流量 Q      = {Q:.4f} ml/s
  喷幅 W      = {W:.2f} m
  {label_area} A = {area:.1f} m²
  用药量 D    = {D:.4f} ml/m²
  稀释倍数 d  = {d:.1f} 倍

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
计算过程：

① 步速 = Q ÷ (W × d × D)
       = {Q:.4f} ÷ ({W:.2f} × {d:.1f} × {D:.4f})
       = {v:.4f} m/s

② 总喷药量 = D × A × d
           = {D:.4f} × {area:.1f} × {d:.1f}
           = {total:.2f} ml

③ 原液用药量 = D × A
             = {D:.4f} × {area:.1f}
             = {stock:.2f} ml

④ 喷雾时长 = 总喷药量 ÷ Q
           = {total:.2f} ÷ {Q:.4f}
           = {total / Q:.2f} s
"""

    result.spray_duration = total / Q
    result.calculation_detail = detail
    result.mode_description = "已知稀释倍数求解模式（室内）" if is_indoor else "已知稀释倍数求解模式"
    return result


# ==================== 参数校验模块 ====================

def validate_parameters(flow_rate, swath_width, fog_height, space_val,
                        chem_type, dosage_value, active_dosage, active_conc,
                        known_type, known_speed, known_dilution, is_indoor) -> list:
    """
    全参数校验函数

    对所有输入参数进行合法性检查，返回错误列表。
    空列表表示校验通过。

    校验规则：
    1. 设备参数必须为正数（流量、喷幅、雾层高度）
    2. 空间参数必须为正数
    3. 药剂参数根据类型分别校验
    4. 已知条件参数必须为正数
    """
    errors = []

    # 设备参数校验
    if flow_rate is None or flow_rate <= 0:
        errors.append("❌ 喷雾机流量必须大于0")
    if swath_width is None or swath_width <= 0:
        errors.append("❌ 喷幅必须大于0")
    if fog_height is None or fog_height <= 0:
        errors.append("❌ 雾层高度必须大于0")
    if space_val is None or space_val <= 0:
        errors.append("❌ 空间参数数值必须大于0")

    # 药剂参数校验
    if chem_type == "active":
        if active_conc is None or active_conc <= 0:
            errors.append("❌ 总有效成分含量必须大于0")
        if active_dosage is None or active_dosage < 0:
            errors.append("❌ 有效成分用药量不能为负")
    else:
        if dosage_value is None or dosage_value < 0:
            errors.append("❌ 制剂用药量不能为负")

    # 已知条件校验
    if known_type == "speed":
        if is_indoor:
            errors.append("❌ 室内场景不支持已知步速")
        elif known_speed is None or known_speed <= 0:
            errors.append("❌ 步速必须大于0")
    else:
        if known_dilution is None or known_dilution <= 0:
            errors.append("❌ 稀释倍数必须大于0")

    return errors