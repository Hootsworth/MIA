import { defineTheme } from "@astryxdesign/core/theme";
import { defaultThemeSlug, themes } from "./astryx-themes";

const importedTheme = themes[defaultThemeSlug];

export const miaEditorialTheme = defineTheme({
  name: "mia-editorial",
  extends: importedTheme,
  components: {
    heading: {
      "type:display-1": {
        fontFamily: 'Georgia, "Times New Roman", serif',
      },
      "type:display-2": {
        fontFamily: 'Georgia, "Times New Roman", serif',
      },
      "type:display-3": {
        fontFamily: 'Georgia, "Times New Roman", serif',
      },
    },
  },
});
