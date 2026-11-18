const {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails
} = require("amazon-cognito-identity-js");

const https = require("https");

const pool = new CognitoUserPool({
  UserPoolId: "eu-west-1_BZKyKZ2Uk",
  ClientId: "6u2tfv98ro8bbkrub6bn2oarto"
});

const username = process.env.COGNITO_USERNAME;
const password = process.env.COGNITO_PASSWORD;

if (!username || !password) {
  console.error("Username ou password em falta.");
  process.exit(1);
}

const user = new CognitoUser({ Username: username, Pool: pool });

const auth = new AuthenticationDetails({
  Username: username,
  Password: password
});

user.authenticateUser(auth, {
  onSuccess: async (result) => {
    const token = result.getAccessToken().getJwtToken();

    const request = https.request(
      "https://api.thinksmart.pt/api/v1/auth/me",
      {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` }
      },
      (response) => {
        let body = "";
        response.on("data", chunk => body += chunk);
        response.on("end", () => {
          console.log("HTTP:", response.statusCode);
          try {
            const data = JSON.parse(body);
            console.log(JSON.stringify(data, null, 2));
          } catch {
            console.log(body);
          }
        });
      }
    );

    request.on("error", error => console.error(error.message));
    request.end();
  },
  onFailure: (error) => {
    console.error("Autenticação falhou:", error.message);
  },
  newPasswordRequired: () => {
    console.error("A conta exige alteração de password.");
  },
  mfaRequired: () => {
    console.error("A conta exige MFA. É necessário concluir a verificação.");
  }
});
