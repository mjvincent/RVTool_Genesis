import {
  Theme,
  Header,
  HeaderName,
  HeaderNavigation,
  SkipToContent,
  Content,
} from "@carbon/react";

function App() {
  return (
    <Theme theme="white">
      <Header aria-label="RVTool Genesis">
        <SkipToContent />
        <HeaderName href="/" prefix="IBM">
          RVTool Genesis
        </HeaderName>
        <HeaderNavigation aria-label="RVTool Genesis" />
      </Header>
      <Content>
        <p style={{ textAlign: "center", marginTop: "4rem" }}>
          RVTool Genesis — Ready
        </p>
      </Content>
    </Theme>
  );
}

export default App;
