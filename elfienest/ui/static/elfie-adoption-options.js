(function () {
  const anatomyLabels = {
    biped: {
      label: "双足精灵",
      detail: "站立互动更明显，适合聊天、挥手和房间巡游。",
    },
    quadruped: {
      label: "四足精灵",
      detail: "动物感更强，适合低姿态移动、摆尾和陪伴动作。",
    },
  };

  const heightOptions = [
    { value: "short", label: "矮小", detail: "更贴近桌面与床位，动作幅度小。" },
    { value: "standard", label: "标准", detail: "默认比例，适合大多数房间。" },
    { value: "tall", label: "高大", detail: "头像更挺拔，房间里更醒目。" },
  ];

  const buildOptions = [
    { value: "slim", label: "纤细", detail: "轮廓更轻，行动感更敏捷。" },
    { value: "standard", label: "标准", detail: "均衡比例，动作和表情稳定。" },
    { value: "plump", label: "圆润", detail: "身体更饱满，视觉上更柔和。" },
  ];

  const personalityDescriptions = {
    活泼好动: "更主动回应、探索和互动。",
    安静温顺: "回应更克制，陪伴感更稳定。",
    好奇探索: "更关注新物体和环境变化。",
    胆小害羞: "初始反应更谨慎，需要更温和互动。",
    傲娇独立: "更有边界感，偏自主行动。",
    完全随机: "系统随机生成完整人格参数。",
  };

  function anatomyOption(value) {
    return anatomyLabels[value] || { label: value, detail: "自定义动物形态。" };
  }

  function personalityDetail(style) {
    return personalityDescriptions[style] || "使用当前系统预设生成人格参数。";
  }

  window.ElfieAdoptionOptions = {
    anatomyOption,
    buildOptions,
    heightOptions,
    personalityDetail,
  };
})();
