export const state = {
  elfies: [],
  currentId: null,
  session: null,
  selectedTurn: null,
  selectedFocus: "summary",
  detailTab: "summary",
  sending: false,
  foods: [],
  configurationCommand: "",
  previewReady: false,
  previewResults: new Map(),
};

export const emotionLabels = {
  happiness: "快乐",
  sadness: "悲伤",
  fear: "恐惧",
  anger: "愤怒",
  surprise: "惊讶",
  disgust: "厌恶",
  boredom: "无聊",
  jealousy: "嫉妒",
  calm: "平静",
};
