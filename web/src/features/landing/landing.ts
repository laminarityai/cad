import { follow } from "./loop";

follow(document, (query) => matchMedia(query));
