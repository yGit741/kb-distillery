import { StartScreen } from "./StartScreen";

// Only rendered as a page when this build has no Home (Home folds /start in as its "Start here" card; see routes/defs.ts movedTo).
export default StartScreen;
// Home's card reads the guide through routes/modules, so a share build without this screen has no card.
export { StartGuide } from "./StartScreen";
