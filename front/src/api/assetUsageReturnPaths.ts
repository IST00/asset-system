export function localFeishuActionPath(operationRequestId: number, operationType: string): string {
  const resource = operationType.endsWith('_RETURN')
    ? 'asset-return-requests'
    : 'asset-usage-requests'
  return `/${resource}/${operationRequestId}/mock-feishu-action`
}
