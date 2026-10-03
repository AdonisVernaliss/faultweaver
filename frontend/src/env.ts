import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
  FAULTWEAVER_API_URL: {
    schema: (value) => value
  }
});
