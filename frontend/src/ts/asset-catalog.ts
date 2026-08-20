import type { AssetCategory, AssetMetadata } from './types.js';

export interface AssetGroup {
  category: AssetCategory;
  label: string;
  assets: AssetMetadata[];
}

const CATEGORY_ORDER: AssetCategory[] = ['robot', 'primitive', 'prop', 'environment'];

export const ASSET_CATEGORY_LABELS: Record<AssetCategory, string> = {
  primitive: 'Primitives',
  robot: 'Robots',
  prop: 'Props',
  environment: 'Environments',
};

export function categoryForAsset(asset: AssetMetadata): AssetCategory {
  if (asset.category) return asset.category;
  if (asset.type === 'robot') return 'robot';
  if (asset.type === 'terrain') return 'environment';
  if (asset.primitive && asset.source_format !== 'openusd') return 'primitive';
  return 'prop';
}

export function groupAssets(assets: AssetMetadata[], rawQuery = ''): AssetGroup[] {
  const query = rawQuery.trim().toLowerCase();
  const visibleAssets = query
    ? assets.filter((asset) => {
      const category = categoryForAsset(asset);
      return [
        asset.name,
        asset.id,
        asset.primitive,
        asset.source_format,
        asset.type,
        category,
        ASSET_CATEGORY_LABELS[category],
      ].some((value) => String(value ?? '').toLowerCase().includes(query));
    })
    : assets;

  return CATEGORY_ORDER.map((category) => ({
    category,
    label: ASSET_CATEGORY_LABELS[category],
    assets: visibleAssets.filter((asset) => categoryForAsset(asset) === category),
  })).filter((group) => group.assets.length > 0);
}
