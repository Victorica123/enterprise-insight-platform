package com.example.videoplatform.workflow;

/** 用户可修正的上传准入失败：等待已有任务完成后即可继续提交。 */
public class ActiveTaskLimitExceededException extends RuntimeException {

	private final int limit;
	private final long activeCount;

	public ActiveTaskLimitExceededException(int limit, long activeCount) {
		super("当前有 " + activeCount + " 个处理中任务，单用户最多 " + limit
				+ " 个，请等待已有任务完成后再上传");
		this.limit = limit;
		this.activeCount = activeCount;
	}

	public int getLimit() {
		return limit;
	}

	public long getActiveCount() {
		return activeCount;
	}
}
