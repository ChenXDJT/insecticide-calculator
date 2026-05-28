# app.py
"""
杀虫剂配药计算器 - Web 界面层

本模块基于 Streamlit 框架构建用户交互界面，
所有核心计算逻辑委托给 core_calculator 模块处理。
界面层仅负责：参数采集、单位转换调用、结果展示。
"""

import streamlit as st
from core_calculator import (
    convert_flow, convert_length, convert_speed,
    reverse_flow, reverse_speed, reverse_time, reverse_volume,
    SpaceParameter, ChemicalParameter,
    solve_by_speed, solve_by_dilution,
    validate_parameters
)

st.set_page_config(page_title="杀虫剂配药计算器", layout="wide")


def main():
    """主界面函数"""
    st.title("🌿 杀虫剂配药计算器")

    # 侧边栏 - 全局单位偏好设置
    with st.sidebar:
        st.header("⚙️ 全局单位偏好")
        flow_unit = st.selectbox("流量单位", ["ml/s", "ml/min", "L/min", "L/h"], index=1)
        speed_unit = st.selectbox("步速单位", ["m/s", "m/min", "km/h"], index=1)
        time_unit = st.selectbox("时长单位", ["s", "min", "h"], index=1)
        vol_unit = st.selectbox("喷药量/原液量单位", ["ml", "L"], index=1)

    # 三列参数输入布局
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("🔧 设备参数")
        flow_rate = st.number_input("喷雾机流量 *", min_value=0.0, value=7.5, step=0.1)
        swath_width = st.number_input("喷幅 *", min_value=0.0, value=10.0, step=0.1)
        fog_height = st.number_input("雾层高度 *", min_value=0.01, value=2.0, step=0.1)
        length_unit = st.selectbox("长度单位", ["m", "cm"], index=0)

    with col2:
        st.subheader("📐 空间参数（四选一）*")
        space_type = st.radio(
            "选择空间参数",
            ["室内空间 (m³)", "室内面积 (m²)",
             "室外空间 (m³)", "室外面积 (m²)"],
            index=2
        )

        # 根据选择显示对应输入框
        space_val = None
        if space_type == "室内空间 (m³)":
            space_val = st.number_input("室内空间数值 *", min_value=0.0, value=200.0, step=10.0)
        elif space_type == "室内面积 (m²)":
            space_val = st.number_input("室内面积数值 *", min_value=0.0, value=100.0, step=10.0)
        elif space_type == "室外空间 (m³)":
            space_val = st.number_input("室外空间数值 *", min_value=0.0, value=500.0, step=10.0)
        else:
            space_val = st.number_input("室外面积数值 *", min_value=0.0, value=300.0, step=10.0)

        is_indoor = "室内" in space_type

    with col3:
        st.subheader("💊 药剂参数 *")
        chem_type = st.radio("用药量类型", ["制剂用药量", "有效成分用药量"], index=0)

        # 药剂参数动态输入
        dosage_value = None
        active_dosage = None
        active_conc = None

        if chem_type == "有效成分用药量":
            active_conc = st.number_input(
                "总有效成分含量 (%) *",
                min_value=0.1, max_value=100.0,
                value=10.0, step=0.1
            )
            active_dosage = st.number_input(
                "有效成分用药量 (mg/m³) *",
                min_value=0.0, value=50.0, step=1.0
            )
            # 有效成分模式锁定用药量单位为 ml/m³
            if active_conc > 0:
                converted = active_dosage / active_conc / 10
                st.info(f"→ 转换后制剂用药量: **{converted:.4f} ml/m³**")
            dosage_unit = "ml/m³"
        else:
            dosage_value = st.number_input(
                "制剂用药量数值 *",
                min_value=0.0, value=1.0,
                step=0.1, format="%.4f"
            )
            dosage_unit = st.selectbox("用药量单位", ["ml/m³", "ml/m²"], index=0)

    # ==================== 已知条件区域（修复版）====================
    st.subheader("🎯 已知条件 *")

    # 先初始化所有变量，避免 UnboundLocalError
    known_type = "dilution"  # 默认值
    known_speed = None
    known_dilution = None

    if is_indoor:
        st.info("室内场景仅支持「已知稀释倍数」，不计算步速")
        known_type = "dilution"
        known_dilution = st.number_input("稀释倍数数值 *", min_value=0.0, value=500.0, step=10.0)
        # known_speed 保持 None
    else:
        # 室外场景：用户选择已知条件类型
        known_type_display = st.radio(
            "选择已知条件",
            ["已知步速", "已知稀释倍数"],
            index=0,
            horizontal=True
        )
        
        # 统一转换为英文标识符
        if known_type_display == "已知步速":
            known_type = "speed"
            known_speed = st.number_input("步速数值 *", min_value=0.0, value=1.0, step=0.1)
            # known_dilution 保持 None
        else:
            known_type = "dilution"
            known_dilution = st.number_input("稀释倍数数值 *", min_value=0.0, value=500.0, step=10.0)
            # known_speed 保持 None

    # 计算按钮
    st.divider()
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        calc_btn = st.button("🚀 开始计算", use_container_width=True)

    # 计算逻辑
    if calc_btn:
        # 参数校验
        errors = validate_parameters(
            flow_rate, swath_width, fog_height, space_val,
            chem_type, dosage_value, active_dosage, active_conc,
            known_type, known_speed, known_dilution, is_indoor
        )

        if errors:
            st.error("**参数校验失败，请补充以下信息：**\n\n" + "\n".join(errors))
        else:
            try:
                # 单位转换至标准单位
                Q = convert_flow(flow_rate, flow_unit)
                W = convert_length(swath_width, length_unit)
                H = convert_length(fog_height, length_unit)

                # 构建空间参数对象
                space = SpaceParameter(space_type, space_val, H)

                # 构建药剂参数对象
                chemical = ChemicalParameter(
                    chem_type=chem_type,
                    dosage_value=dosage_value,
                    active_dosage=active_dosage,
                    active_conc=active_conc
                )

                # 调用求解引擎
                if known_type == "speed":
                    v_ms = convert_speed(known_speed, speed_unit)
                    result = solve_by_speed(Q, W, H, space, chemical, v_ms, dosage_unit)
                else:
                    result = solve_by_dilution(
                        Q, W, H, space, chemical,
                        known_dilution, dosage_unit, is_indoor
                    )

                # 结果展示
                display_results(result, vol_unit, speed_unit, time_unit, is_indoor)

            except Exception as e:
                st.error(f"计算过程发生错误：{str(e)}")


def display_results(result, vol_unit, speed_unit, time_unit, is_indoor):
    """
    统一展示计算结果

    Args:
        result: CalculationResult 计算结果对象
        vol_unit: 体积显示单位
        speed_unit: 速度显示单位
        time_unit: 时间显示单位
        is_indoor: 是否为室内场景
    """
    st.divider()
    st.success(f"**计算完成！** {result.mode_description}")

    # 结果指标卡片
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("总喷药量",
                  f"{reverse_volume(result.total_spray, vol_unit):.2f} {vol_unit}")
    with c2:
        st.metric("原液用药量",
                  f"{reverse_volume(result.stock_solution, vol_unit):.2f} {vol_unit}")
    with c3:
        st.metric("稀释倍数",
                  f"{result.dilution_ratio:.1f} 倍")
    with c4:
        if is_indoor:
            st.metric("步速", "—")
        else:
            st.metric("步速",
                      f"{reverse_speed(result.walking_speed, speed_unit):.2f} {speed_unit}")
    with c5:
        st.metric("喷雾时长",
                  f"{reverse_time(result.spray_duration, time_unit):.2f} {time_unit}")

    # 详细计算过程
    with st.expander("📋 查看详细计算过程", expanded=True):
        st.text(result.calculation_detail)

    # 公式说明
    with st.expander("📖 公式说明"):
        st.markdown("""
**核心公式体系：**

- **制剂用药量** = 有效成分用药量(mg/m³) ÷ 含量(%) ÷ 10
- **空间自动换算** = 面积(m²) × 雾层高度(m) ⟷ 体积(m³) ÷ 雾层高度(m)
- **总喷药量(体积法)** = 用药量(ml/m³) × 空间(m³) × 稀释倍数
- **总喷药量(面积法)** = 用药量(ml/m²) × 面积(m²) × 稀释倍数
- **稀释倍数(体积法)** = 流量 ÷ (喷幅 × 雾层高度 × 步速 × 用药量)
- **稀释倍数(面积法)** = 流量 ÷ (喷幅 × 步速 × 用药量)
- **步速(体积法)** = 流量 ÷ (喷幅 × 雾层高度 × 稀释倍数 × 用药量)
- **步速(面积法)** = 流量 ÷ (喷幅 × 稀释倍数 × 用药量)
- **喷雾时长** = 总喷药量 ÷ 流量
- **原液用药量** = 用药量 × 空间(或面积)

**业务规则：**
- 室内场景禁用步速计算，仅支持已知稀释倍数模式
- 空间参数四选一，系统自动通过雾层高度完成体积-面积换算
        """)


if __name__ == "__main__":
    main()
