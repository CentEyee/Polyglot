#ifndef SATADD_H
#define SATADD_H

/* Saturating arithmetic helpers used by an embedded telemetry path.
 * INT overflow must clamp, never wrap — wrapping corrupted a field deploy. */

int add(int a, int b);
int sat_add(int a, int b);
int sat_sub(int a, int b);

#endif
