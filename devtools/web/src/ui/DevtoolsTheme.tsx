import { App, ConfigProvider, theme } from "antd";

type Props = Readonly<{
  readonly children: React.ReactNode;
  readonly mode: "light" | "dark";
}>;

const sharedToken = {
  borderRadius: 8,
  controlHeight: 38,
  controlHeightLG: 44,
  fontFamily: '"Avenir Next", "Noto Sans CJK SC", "PingFang SC", "Helvetica Neue", Arial, sans-serif',
  fontSize: 14,
  lineWidth: 1,
} as const;

export function DevtoolsTheme({ children, mode }: Props): React.JSX.Element {
  const dark = mode === "dark";
  return <ConfigProvider
    componentSize="middle"
    theme={{
      algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        ...sharedToken,
        colorBgBase: dark ? "#101a18" : "#f1f6f3",
        colorBgContainer: dark ? "#182a25" : "#ffffff",
        colorBgElevated: dark ? "#1d302a" : "#ffffff",
        colorBorder: dark ? "#46675c" : "#cbd8d1",
        colorError: dark ? "#ef9991" : "#b43c3c",
        colorPrimary: dark ? "#74c799" : "#217a5c",
        colorText: dark ? "#dce8e2" : "#1a2821",
        colorTextSecondary: dark ? "#a9bbb3" : "#4e6258",
        colorTextTertiary: dark ? "#80978d" : "#778a80",
      },
      components: {
        Button: {
          defaultBg: dark ? "#1b332d" : "#ffffff",
          defaultBorderColor: dark ? "#537b6e" : "#cbd8d1",
          defaultColor: dark ? "#dce8e2" : "#4e6258",
          fontWeight: 650,
        },
        Drawer: { paddingLG: 0 },
        Input: {
          activeBorderColor: dark ? "#74c799" : "#217a5c",
          hoverBorderColor: dark ? "#74c799" : "#43aa84",
        },
        Modal: { padding: 0 },
        Select: {
          optionSelectedBg: dark ? "#29463b" : "#dff0e8",
          optionSelectedColor: dark ? "#f4fbf7" : "#1a2821",
        },
        Table: {
          headerBg: dark ? "#20362f" : "#f8faf9",
          headerColor: dark ? "#c4d4cd" : "#4e6258",
          rowHoverBg: dark ? "#213b32" : "#f3faf6",
        },
      },
    }}
  >
    <App className={`devtools-app devtools-app-${mode}`}>{children}</App>
  </ConfigProvider>;
}
