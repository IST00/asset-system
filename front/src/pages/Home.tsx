import { Card, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { helloApi } from '@/api'

export default function Home() {
  const { data, isLoading } = useQuery({
    queryKey: ['hello'],
    queryFn: () => helloApi.hello(),
  })

  return (
    <Card title="Home">
      <Typography.Paragraph>
        Backend says: <strong>{isLoading ? 'Loading...' : data}</strong>
      </Typography.Paragraph>
    </Card>
  )
}
