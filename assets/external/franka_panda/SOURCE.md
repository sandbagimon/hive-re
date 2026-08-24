# Franka Panda OpenUSD source

The original asset was downloaded from NVIDIA Isaac Sim 5.1:

`https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd`

NVIDIA's Isaac Sim robot asset catalog identifies the Franka Panda model as
Apache-2.0 licensed. `franka_quality.usdc` is a flattened, relocatable copy of
the authored `Mesh=Quality` and `Gripper=Default` variants. It preserves the
OpenUSD physics links, joints, mass properties, collision meshes, and detailed
render meshes used by BeeFoundrySim.

The duplicated cable decoration composed at the Link0 root was omitted because
its transform depends on Isaac-specific composition behavior and placed the
decoration below the robot when resolved by the standard OpenUSD core resolver.
The detailed link meshes and correctly positioned logo remain intact.

The Isaac-specific `OmniPBR.mdl` shader is intentionally not required by the
web renderer. BeeFoundrySim uses cached mesh geometry and authored display colors.
