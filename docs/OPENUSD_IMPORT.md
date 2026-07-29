# OpenUSD 导入指南

## 支持的入口方式

Web 编辑器提供两个入口：

- **Import USD**：导入单个 `.usd`、`.usda`、`.usdc`、`.usdz` 或 `.zip` 包。
- **Import USD Folder**：上传完整目录并保留 Sublayer、Reference、Payload、纹理等相对路径。

目录中只有一个最浅层 USD 文件时，该文件自动成为 Stage 入口；存在多个同层候选时，前端要求用户明确选择。ZIP 包包含多个同层候选时，API 调用方必须提供 `package_entry`。推荐交换复杂资产时优先使用自包含 `.usdz` 或完整目录。

## HTTP API

接口：

```text
POST /api/v1/projects/{project_id}/assets/openusd
Content-Type: multipart/form-data
```

字段：

| 字段 | 必需 | 含义 |
|---|---:|---|
| `entry` | 是 | 上传文件中的入口 USD 或 ZIP 相对路径 |
| `files` | 是 | 一个或多个文件；filename 必须保留相对路径 |
| `package_entry` | 否 | ZIP 内部入口 USD 相对路径 |

目录上传示例：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/projects/PROJECT_ID/assets/openusd \
  -F 'entry=factory/Factory.usd' \
  -F 'files=@Factory.usd;filename=factory/Factory.usd' \
  -F 'files=@SubUSDs/Floor.usd;filename=factory/SubUSDs/Floor.usd' \
  -F 'files=@textures/albedo.png;filename=factory/textures/albedo.png'
```

为了兼容已有客户端，接口仍接受原来的 Base64 JSON 请求；新客户端应使用 multipart，避免 Base64 体积膨胀和额外内存副本。

## 导入流水线

```text
multipart files / USDZ / safe ZIP
              |
              v
安全暂存与路径校验
              |
              v
OpenUSD Stage composition
              |
       +------+------+
       |             |
       v             v
视觉几何提取     碰撞几何提取
       |             |
       +------+------+
              v
项目内可迁移缓存
  - source dependencies
  - visual.json
  - collision.obj
  - manifest.json
              |
              v
Asset metadata + opaque artifact IDs
```

上传暂存目录在成功或失败后都会清理。项目缓存保留入口文件和已解析依赖，不把浏览器路径或服务器绝对路径写入公共 API。

## 当前支持范围

### Stage 与几何

- Stage Transform 层级；
- `metersPerUnit`；
- Y-up 到 Z-up 转换；
- 多边形 `UsdGeomMesh` 三角化；
- Cube、Sphere、Cylinder、Cone、Capsule 网格化；
- 默认时间点的 PointInstancer 展开；
- Vertex、Varying、Uniform 和 Face-Varying UV；
- 浏览器端法线重建。

### 材质与纹理

- `primvars:displayColor` 和 `displayOpacity`；
- 绑定的 `UsdPreviewSurface` diffuse color 和 opacity；
- 连接到 `UsdUVTexture` 的首个 base-color texture；
- 纹理作为鉴权 Artifact 下载并应用到 Three.js 材质；
- 缺失纹理或 MDL 时回退到颜色或默认材质。

### 物理与碰撞

- Rigid Body dynamic/kinematic 状态；
- Mass、Density、Friction 和 Restitution 元数据；
- 优先使用应用了 `PhysicsCollisionAPI` 的专用碰撞几何；
- 没有专用碰撞几何时明确警告并回退到视觉网格；
- 生成 OBJ 碰撞网格供 MJCF/MuJoCo 使用。

### Robot Articulation

- 固定和 Revolute Joint 子集；
- Link、Collider、Inertial、Position Drive；
- 项目内依赖复制和可迁移 source URI；
- Robotics cache、Import Report 和 Manifest。

## 依赖错误策略

结构依赖和外观依赖采用不同策略：

| 依赖类型 | 缺失后的行为 |
|---|---|
| Sublayer、Reference、Payload、USD 文件 | 阻止导入，避免产生不完整场景 |
| Texture、MDL、MaterialX 外观文件 | 发出警告，继续导入几何并使用回退材质 |

错误响应包含稳定的 Import Report：

```json
{
  "source_path": "...",
  "issues": [
    {
      "severity": "error",
      "code": "usd.missing_dependency",
      "prim_path": "/World/Asset",
      "field": "payload",
      "message": "...",
      "fallback": null
    }
  ],
  "resolved_dependencies": [],
  "unresolved_dependencies": [],
  "has_errors": true
}
```

## 安全限制

- 最大上传或 ZIP 解压总量：256 MiB；
- 最大文件/ZIP Entry 数：4096；
- 拒绝绝对路径、`..`、Windows Drive 路径和重复路径；
- 拒绝 ZIP 符号链接和 ZIP 路径穿越；
- Python Controller 开关与 OpenUSD 导入互相独立；导入 USD 不执行 Python；
- 远程部署仍需由反向代理设置请求体、超时和速率限制。

## 已知限制

- 目前只应用第一个可解析的 base-color texture，不支持完整多材质分组和复杂 Shader Graph；
- 不支持骨骼蒙皮、动画回放、Variants 编辑和运行时 USD Composition 编辑；
- PointInstancer 在默认时间点展开，不保存实例语义；
- 不提供凸分解、SDF 或自动低模碰撞生成；
- OpenUSD Robot Articulation 仍限制在文档声明的 Joint/Drive 子集；
- 超大资产仍建议在上传前进行打包、减面和碰撞简化。

## 验证

```bash
python -m pytest \
  tests/test_openusd_stage_loader.py \
  tests/test_openusd_importer.py \
  tests/test_openusd_upload_bundle.py \
  tests/test_openusd_articulation_importer.py \
  tests/test_openusd_robot_asset_importer.py

npm run test:web -- --grep "OpenUSD folder"
```
