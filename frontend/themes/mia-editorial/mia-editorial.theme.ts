// The mia-editorial theme. `astryx experimental theme editor` wrote this file once and never changes it again.
// The checked settings live in mia-editorial.settings.json and the generated mia-editorial.settings.ts;
// change them with `astryx experimental theme editor set mia-editorial ...`. Add your own changes below: they win over the settings.
import {defineTheme} from '@astryxdesign/core/theme';
import {miaEditorialSettings} from './mia-editorial.settings';

export const miaEditorialTheme = defineTheme({
  extends: miaEditorialSettings,
  name: 'mia-editorial',
});
