import { ApiOutlined, TeamOutlined } from '@ant-design/icons'
import { Alert, Card, ConfigProvider, Flex, Layout, Space, Tag, Typography } from 'antd'

const { Content, Header } = Layout
const { Paragraph, Text, Title } = Typography

export function App() {
  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#e5484d', borderRadius: 10 } }}>
      <Layout className="app-shell">
        <Header className="app-header">
          <Space>
            <TeamOutlined />
            <Text className="app-title">DNF 团长排表工具</Text>
            <Tag color="processing">阶段 0</Tag>
          </Space>
        </Header>
        <Content className="app-content">
          <Card className="welcome-card">
            <Flex vertical gap={20}>
              <div>
                <Title level={2}>工程基线已就绪</Title>
                <Paragraph type="secondary">
                  面向 DNF 国服 PC 端的版本化副本管理和通用排表基础工程。
                </Paragraph>
              </div>
              <Alert
                type="success"
                showIcon
                icon={<ApiOutlined />}
                message="前端开发服务已启动"
                description="后端探针：/api/v1/health/live；API 文档：/docs"
              />
            </Flex>
          </Card>
        </Content>
      </Layout>
    </ConfigProvider>
  )
}
