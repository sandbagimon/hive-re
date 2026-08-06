# USDZ PBR Material Fidelity

日期：2026-08-05  
提交：待提交

## 目标

让服务器资产库中的 USDZ 普通 Mesh 在 Three.js 视口恢复作者态外观，消除包内纹理未被缓存导致的白模，并让同一流程适用于后续单材质 `UsdPreviewSurface` 资产。

## 根因

OpenUSD Resolver 将 USDZ 内部纹理表示为 `asset.usdz[textures/file.png]`。旧缓存器使用普通 `Path.is_file()` 判断依赖，这类 package-relative path 因而被跳过。`anime_test` 没有常量 `displayColor`，基础色完全来自纹理；纹理丢失后只能回退为白色。

## 主要改动

- 通过 OpenUSD `ArResolver` 读取 USDZ package member，并在验证外层包和内部相对路径后写入可迁移项目缓存。
- 从 `UsdPreviewSurface` 提取 base-color、normal、roughness、metallic 连接及对应标量回退。
- 扩展 `visual.json`、几何 API 和 artifact 外部化字段，四类贴图保持独立鉴权下载。
- 前端并行下载四类纹理；基础色使用 sRGB，数据贴图使用线性色彩空间，并绑定到 `MeshStandardMaterial` 的 `map`、`normalMap`、`roughnessMap` 和 `metalnessMap`。
- 重新导入 `anime_test.usdz`，更新共享资产 metadata 与正式缓存。
- 使用同一流水线登记 `sea.usdz` 与 `fan.usdz`，验证后续服务器侧 USDZ 可以直接进入共享资产库。

## 验证

- 合成 USDZ 回归测试验证四类 package-member 纹理内容完整写入缓存。
- API 回归测试验证四类纹理均被外部化为独立 artifact 且可鉴权下载。
- TypeScript 类型检查与生产构建通过。
- Python 全量回归：266 passed、3 skipped；Ruff 与 mypy 通过。
- 前端模块回归全部通过；Playwright 17 个完整浏览器工作流全部通过。
- 真实浏览器验证：`anime_test` 几何响应包含四个 artifact，四个 PNG 请求均返回 HTTP 200。
- Three.js 截图确认人物基础色、发色、服装颜色和 PBR 明暗细节恢复，不再是白模。
- `sea` 与 `fan` 均完成真实浏览器加载：几何接口成功，每项四个 PBR 纹理请求全部 HTTP 200。

## 已知限制

- 普通 Mesh 仍会将多材质几何压平为一个视口材质；本轮完整覆盖 `anime_test` 使用的单材质 `UsdPreviewSurface` 路径。
- 复杂 MaterialX/MDL 图、骨骼蒙皮和动画仍不在当前导入范围。
- USD DomeLight/HDR 不覆盖编辑器全局环境，避免单个资产改变整个场景照明。

## 下一步

- 为多材质 Mesh 增加 material table、geometry groups 和多材质 Three.js 渲染。
- 根据真实资产需求继续支持 emissive、opacity map、UV transform 和 sampler wrap 配置。
