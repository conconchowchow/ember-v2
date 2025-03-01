import abc
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.ember.core.registry.model.base.schemas.model_info import ModelInfo
from src.ember.core.registry.model.base.schemas.chat_schemas import (
    ChatRequest,
    ChatResponse,
)


class BaseChatParameters(BaseModel):
    """Base chat parameters for provider-specific implementations.

    Providers should inherit from this class to manage common fields such as prompt,
    context, temperature, and token limitations, tweaking the naming and doing validation
    as needed and according to their own API-specific requirements.

    Attributes:
        prompt (str): The user prompt text.
        context (Optional[str]): Additional context to be prepended to the prompt.
        temperature (Optional[float]): Sampling temperature with a value between 0.0 and 2.0.
        max_tokens (Optional[int]): Optional maximum token count for responses.
    """

    prompt: str
    context: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = None

    def build_prompt(self) -> str:
        """Build the final prompt by combining context and the user prompt.

        Returns:
            str: The constructed prompt with context included when provided.
        """
        if self.context:
            return "{context}\n\n{prompt}".format(
                context=self.context, prompt=self.prompt
            )
        return self.prompt


class BaseProviderModel(abc.ABC):
    """Base class for all provider implementations.

    This abstract class defines the contract for creating an API client and
    processing chat requests. Subclasses must implement the methods to create
    their respective clients and to handle chat requests.
    """

    def __init__(self, model_info: ModelInfo) -> None:
        """Initialize the provider model with the given model information.

        Args:
            model_info (ModelInfo): Metadata and configuration details for the model.
        """
        self.model_info: ModelInfo = model_info
        self.client: Any = self.create_client()

    @abc.abstractmethod
    def create_client(self) -> Any:
        """Create and configure the API client.

        Subclasses must override this method to initialize and return their API client.

        Returns:
            Any: A configured API client instance.
        """
        raise NotImplementedError("Subclasses must implement create_client")

    @abc.abstractmethod
    def forward(self, request: ChatRequest) -> ChatResponse:
        """Process the chat request and return the corresponding response.

        Args:
            request (ChatRequest): The chat request containing the prompt and additional parameters.

        Returns:
            ChatResponse: The response generated by the provider.
        """
        raise NotImplementedError("Subclasses must implement forward")

    def __call__(self, prompt: str, **kwargs: Any) -> ChatResponse:
        """Allow the instance to be called as a function to process a prompt.

        This method constructs a ChatRequest using the prompt and keyword arguments,
        and then delegates the request processing to the forward() method.

        Args:
            prompt (str): The chat prompt to send.
            **kwargs (Any): Additional parameters to pass into the ChatRequest.

        Returns:
            ChatResponse: The response produced by processing the chat request.
        """
        chat_request: ChatRequest = ChatRequest(prompt=prompt, **kwargs)
        return self.forward(request=chat_request)
