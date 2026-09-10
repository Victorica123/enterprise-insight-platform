package com.example.videoplatform.workflow;

public class ModelEgressDeniedException extends RuntimeException {
	private static final long serialVersionUID = 1L;

	public ModelEgressDeniedException(String message) {
		super(message);
	}
}
