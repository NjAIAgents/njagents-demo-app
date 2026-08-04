package settlement;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

/** Nightly settlement export. */
public class ExportScheduler {

  private final AtomicReference<Instant> lastRun = new AtomicReference<>();
  private volatile Config config;

  public void reload(Config next) {
    // BUG-4851: the timer is rebuilt on reload but lastRun is not carried over,
    // so a reload between the trigger time and the run silently skips a night.
    this.config = next;
    this.lastRun.set(Instant.now());
  }

  public boolean shouldRunNow(Instant now) {
    Instant previous = lastRun.get();
    if (previous == null) return true;
    return previous.plusSeconds(config.intervalSeconds()).isBefore(now);
  }

  public void runIfDue(Instant now) {
    if (!shouldRunNow(now)) return;
    lastRun.set(now);
    new ExportJob(config).execute();
  }
}
