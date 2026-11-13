const { handlePagesRequest } = require("../lib/cf_adapter");
const { handler } = require("../lib/api");

exports.onRequest = async (context) => handlePagesRequest(context, handler);
