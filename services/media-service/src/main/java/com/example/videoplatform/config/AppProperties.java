package com.example.videoplatform.config;

/** Compatibility facade; new components may inject the domain properties directly. */
public class AppProperties {
	private final JwtProperties jwt;
	private final OidcProperties oidc;
	private final StorageProperties storage;
	private final WorkflowProperties workflow;
	private final QuotaProperties quota;
	private final MqProperties mq;
	private final TranscriptProperties transcript;
	private final SummaryProperties summary;
	private final SecurityProperties security;
	private final IntegrationProperties integration;
	private final ModelEgressProperties modelEgress;
	private final RetentionProperties retention;

	public AppProperties() {
		this(new JwtProperties(), new OidcProperties(), new StorageProperties(), new WorkflowProperties(), new QuotaProperties(), new MqProperties(), new TranscriptProperties(), new SummaryProperties(), new SecurityProperties(), new IntegrationProperties(), new ModelEgressProperties(), new RetentionProperties());
	}

	public AppProperties(JwtProperties jwt,
			OidcProperties oidc,
			StorageProperties storage,
			WorkflowProperties workflow,
			QuotaProperties quota,
			MqProperties mq,
			TranscriptProperties transcript,
			SummaryProperties summary,
			SecurityProperties security,
			IntegrationProperties integration,
			ModelEgressProperties modelEgress,
			RetentionProperties retention) {
		this.jwt = jwt;
		this.oidc = oidc;
		this.storage = storage;
		this.workflow = workflow;
		this.quota = quota;
		this.mq = mq;
		this.transcript = transcript;
		this.summary = summary;
		this.security = security;
		this.integration = integration;
		this.modelEgress = modelEgress;
		this.retention = retention;
	}

	public JwtProperties getJwt() { return jwt; }

	public OidcProperties getOidc() { return oidc; }

	public StorageProperties getStorage() { return storage; }

	public WorkflowProperties getWorkflow() { return workflow; }

	public QuotaProperties getQuota() { return quota; }

	public MqProperties getMq() { return mq; }

	public TranscriptProperties getTranscript() { return transcript; }

	public SummaryProperties getSummary() { return summary; }

	public SecurityProperties getSecurity() { return security; }

	public IntegrationProperties getIntegration() { return integration; }

	public ModelEgressProperties getModelEgress() { return modelEgress; }

	public RetentionProperties getRetention() { return retention; }

	// Preserve source references such as AppProperties.Storage.S3.
	public static class Jwt extends JwtProperties { }
	public static class Oidc extends OidcProperties { }
	public static class Storage extends StorageProperties { }
	public static class Workflow extends WorkflowProperties { }
	public static class Quota extends QuotaProperties { }
	public static class Mq extends MqProperties { }
	public static class Transcript extends TranscriptProperties { }
	public static class Summary extends SummaryProperties { }
	public static class Security extends SecurityProperties { }
	public static class Integration extends IntegrationProperties { }
	public static class ModelEgress extends ModelEgressProperties { }
	public static class Retention extends RetentionProperties { }
	public static class Feature extends FeatureProperties { }
}
