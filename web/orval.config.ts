import type { Config } from "orval"

const config: Config = {
  rentgraph: {
    input: {
      target: "../server/openapi.json",
    },
    output: {
      target: "src/api/generated",
      schemas: "src/api/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        fetch: {
          includeHttpResponseReturnType: false,
          // 非 2xx 统一抛 Error（错误体挂在 err.info / err.status），
          // 否则 422 NO_TEXT_LAYER 会被当成 ContractOut 继续 analyze，演示直接翻车
          forceSuccessResponse: true,
        },
      },
    },
  },
}

export default config
